"""Submit managed JPEGs to validated CUPS queues with allowlisted options."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
import logging
from pathlib import Path
import re
import tempfile
from typing import Final
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from photobooth.printing.contract import (
    PhysicalPrinterStatus,
    PrintError,
    PrintJobState,
    PrintResult,
    PrinterUnavailableError,
    PrintStatus,
)
from photobooth.printing.process import (
    PrintProcessLaunchError,
    PrintProcessRunner,
    PrintProcessTimeoutError,
    SubprocessPrintProcessRunner,
)
from photobooth.printing.settings import PrinterBackendKind, PrintingSettings

_COMMAND_TIMEOUT_SECONDS: Final[float] = 15.0
_CP1000_USB_VENDOR_ID: Final[str] = "04a9"
_CP1000_USB_PRODUCT_ID: Final[str] = "32ae"
_LSUSB_DEVICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"Bus [0-9]{3} Device [0-9]{3}: ID ([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})(?:\s+.+)?\Z"
)
_JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.-]+-[0-9]+\Z")
_JOB_RESPONSE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\brequest id is\s+([A-Za-z0-9_.-]+-[0-9]+)\b", re.IGNORECASE
)
_LOGGER = logging.getLogger(__name__)


class QueueStatus(str, Enum):
    """Describe whether a configured CUPS queue can accept print jobs."""

    AVAILABLE = "available"
    DISABLED = "disabled"
    NOT_FOUND = "not-found"
    NO_QUEUES = "no-queues"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not-configured"


@dataclass(frozen=True)
class CupsDiagnostics:
    """Expose CUPS queue and independent USB-presence diagnostics to administration."""

    lp_available: bool
    lpstat_available: bool
    lpoptions_available: bool
    cups_available: bool
    queues: tuple[str, ...]
    queue_status: QueueStatus
    physical_printer_status: PhysicalPrinterStatus
    physical_printer_error: str | None
    queue_description: str | None
    queue_model: str | None
    capabilities: dict[str, tuple[str, ...]]
    unsupported_options: tuple[str, ...]
    error: str | None


class CupsPrinterBackend:
    """Own CUPS discovery, option validation, submission, and status queries.

    The backend runs only finite system commands and never imports CUPS
    bindings. It validates queue names and driver capabilities before `lp`,
    writes the supplied original JPEG bytes to a temporary file for the
    duration of the `lp` call, and does not infer physical output from
    submission or CUPS completion. A queue can persist while its printer is
    disconnected, so each submission also checks for the observed CP1000 USB
    vendor/product ID (`04a9:32ae`). This proves USB visibility only, not paper
    or consumable readiness.
    """

    _OPTION_NAMES: Final[tuple[tuple[str, str], ...]] = (
        ("page_size", "PageSize"),
        ("color_model", "ColorModel"),
        ("resolution", "Resolution"),
        ("image_type", "StpImageType"),
        ("borderless", "StpBorderless"),
        ("page_fit", "StpiShrinkOutput"),
        ("color_precision", "StpColorPrecision"),
        ("color_correction", "StpColorCorrection"),
        ("legacy_dyesub_gamma", "StpLegacyDyesubGamma"),
        ("brightness", "StpBrightness"),
        ("contrast", "StpContrast"),
        ("saturation", "StpSaturation"),
        ("gamma", "StpGamma"),
    )

    def __init__(
        self,
        settings: PrintingSettings,
        process_runner: PrintProcessRunner | None = None,
    ) -> None:
        """Select validated settings and an injectable finite-command runner."""
        self._settings = settings
        self._runner = (
            process_runner
            if process_runner is not None
            else SubprocessPrintProcessRunner()
        )

    def list_queues(self) -> tuple[str, ...]:
        """Return CUPS-reported queues without assuming a specific printer model."""
        self._ensure_service()
        output = self._run("lpstat", ("-e",))
        queues = tuple(
            sorted(
                line.strip()
                for line in output.stdout.splitlines()
                if line.strip() and _safe_queue_name(line.strip())
            )
        )
        _LOGGER.info("Discovered %d CUPS printer queues", len(queues))
        return queues

    def get_diagnostics(self) -> CupsDiagnostics:
        """Collect bounded CUPS and, when selected, physical-presence diagnostics."""
        lp_available = self._runner.find_executable("lp") is not None
        lpstat_available = self._runner.find_executable("lpstat") is not None
        lpoptions_available = self._runner.find_executable("lpoptions") is not None
        cups_available = False
        queues: tuple[str, ...] = ()
        queue_status = (
            QueueStatus.UNAVAILABLE
            if self._settings.queue_name
            else QueueStatus.NOT_CONFIGURED
        )
        description: str | None = None
        model: str | None = None
        capabilities: dict[str, tuple[str, ...]] = {}
        unsupported_options: tuple[str, ...] = ()
        error: str | None = None
        physical_status = PhysicalPrinterStatus.NOT_CHECKED
        physical_error: str | None = None
        try:
            queues = self.list_queues()
            cups_available = True
            if self._settings.queue_name:
                queue_status, description = self.get_queue_status(
                    self._settings.queue_name
                )
                if queue_status is QueueStatus.AVAILABLE:
                    model = self._queue_model(self._settings.queue_name)
                    if lpoptions_available:
                        capabilities = self.get_supported_options(self._settings.queue_name)
                        unsupported_options = tuple(
                            option_name
                            for option_name, value in self.options_for_settings().items()
                            if value not in capabilities.get(option_name, ())
                        )
                    else:
                        error = "The CUPS `lpoptions` command is unavailable."
        except PrintError as print_error:
            error = str(print_error)
        if self._settings.backend is PrinterBackendKind.CUPS:
            physical_status, physical_error = self._physical_printer_status()
        return CupsDiagnostics(
            lp_available=lp_available,
            lpstat_available=lpstat_available,
            lpoptions_available=lpoptions_available,
            cups_available=cups_available,
            queues=queues,
            queue_status=queue_status,
            physical_printer_status=physical_status,
            physical_printer_error=physical_error,
            queue_description=description,
            queue_model=model,
            capabilities=capabilities,
            unsupported_options=unsupported_options,
            error=error,
        )

    def get_queue_status(self, queue_name: str) -> tuple[QueueStatus, str | None]:
        """Validate one queue and report its accepting and enabled state."""
        _validate_queue_name(queue_name)
        queues = self.list_queues()
        if not queues:
            return QueueStatus.NO_QUEUES, None
        if queue_name not in queues:
            return QueueStatus.NOT_FOUND, None
        printer = self._run("lpstat", ("-l", "-p", queue_name))
        accepting = self._run("lpstat", ("-a", queue_name))
        printer_text = printer.stdout.casefold()
        accepting_text = accepting.stdout.casefold()
        if (
            "disabled" in printer_text
            or " is stopped" in printer_text
            or "not accepting" in accepting_text
        ):
            status = QueueStatus.DISABLED
        elif " enabled " in f" {printer_text} " and " accepting requests" in accepting_text:
            status = QueueStatus.AVAILABLE
        else:
            status = QueueStatus.DISABLED
        description = _description(printer.stdout)
        return status, description

    def get_supported_options(self, queue_name: str) -> dict[str, tuple[str, ...]]:
        """Return supported queue option values from bounded `lpoptions` output."""
        _validate_queue_name(queue_name)
        output = self._run("lpoptions", ("-p", queue_name, "-l"))
        options = _parse_options(output.stdout)
        if not options:
            raise PrintError("The printer did not report supported print options.")
        return options

    def validate_settings(self) -> None:
        """Require an enabled configured queue and every selected option value."""
        if not self._settings.queue_name:
            raise PrintError("Choose a CUPS printer queue in administration.")
        _LOGGER.info("Validating configured CUPS queue %s", self._settings.queue_name)
        queue_status, _ = self.get_queue_status(self._settings.queue_name)
        if queue_status is QueueStatus.NO_QUEUES:
            raise PrintError("CUPS has no configured printer queues.")
        if queue_status is QueueStatus.NOT_FOUND:
            raise PrintError("The configured CUPS printer queue was not found.")
        if queue_status is not QueueStatus.AVAILABLE:
            raise PrintError("The configured CUPS printer queue is unavailable.")
        supported = self.get_supported_options(self._settings.queue_name)
        for option_name, value in self.options_for_settings().items():
            choices = supported.get(option_name)
            if choices is None:
                raise PrintError(f"The selected printer does not support {option_name}.")
            if value not in choices:
                raise PrintError(
                    f"The selected printer does not support the configured {option_name} value."
                )

    def options_for_settings(self) -> dict[str, str]:
        """Map typed settings to only the allowlisted CUPS/Gutenprint options."""
        settings_values: dict[str, str] = {
            "page_size": self._settings.page_size.value,
            "color_model": self._settings.color_model.value,
            "resolution": self._settings.resolution.value,
            "image_type": self._settings.image_type.value,
            "borderless": str(self._settings.borderless),
            "page_fit": self._settings.page_fit.value,
            "color_precision": self._settings.color_precision.value,
            "color_correction": self._settings.color_correction.value,
            "legacy_dyesub_gamma": str(self._settings.legacy_dyesub_gamma),
            "brightness": _adjustment_option(self._settings.brightness),
            "contrast": _adjustment_option(self._settings.contrast),
            "saturation": _adjustment_option(self._settings.saturation),
            "gamma": _adjustment_option(self._settings.gamma),
        }
        return {
            option_name: settings_values[field_name]
            for field_name, option_name in self._OPTION_NAMES
        }

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Validate, stage, and submit one JPEG; timeout outcomes remain uncertain."""
        del idempotency_key
        if not self._settings.enabled:
            raise PrintError("Printing is disabled in administration.")
        command = self._require_cups_commands()
        self.validate_settings()
        physical_status, physical_error = self._physical_printer_status()
        if physical_status is not PhysicalPrinterStatus.CONNECTED:
            raise PrinterUnavailableError(
                physical_error
                or "The Canon SELPHY CP1000 was not detected over USB."
            )
        if not _is_jpeg(image_data):
            raise PrintError("The selected photo is not a valid JPEG.")
        options = self.options_for_settings()
        _LOGGER.info(
            "Submitting photo to CUPS queue %s with options %s",
            self._settings.queue_name,
            options,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="photobooth-print-") as directory:
                photo_path = Path(directory) / "photo.jpg"
                photo_path.write_bytes(image_data)
                arguments = [
                    command,
                    "-d",
                    self._settings.queue_name,
                ]
                for name, value in options.items():
                    arguments.extend(("-o", f"{name}={value}"))
                arguments.append(str(photo_path))
                output = self._run_command(arguments, "lp")
        except PrintError:
            raise
        except OSError as error:
            raise PrintError("The photo could not be prepared for printing.") from error
        match = _JOB_RESPONSE_PATTERN.search(output.stdout)
        if match is None or not match.group(1).startswith(
            f"{self._settings.queue_name}-"
        ):
            _LOGGER.error("CUPS accepted no parseable job identifier")
            raise PrintError(
                "The printer response could not be confirmed; check its queue before retrying.",
                uncertain=True,
            )
        job_id = match.group(1)
        _LOGGER.info("CUPS submitted print job %s", job_id)
        return PrintResult(
            status=PrintStatus.SUBMITTED,
            queue_name=self._settings.queue_name,
            job_id=job_id,
            submitted_at=datetime.now(timezone.utc),
            status_text="Photo submitted to the printer.",
        )

    def get_job_status(self, job_id: str) -> PrintJobState:
        """Query a known job while preserving CUPS's limited physical-output semantics."""
        if (
            _JOB_ID_PATTERN.fullmatch(job_id) is None
            or not job_id.startswith(f"{self._settings.queue_name}-")
        ):
            return PrintJobState.UNKNOWN
        queue_status, _ = self.get_queue_status(self._settings.queue_name)
        if queue_status is not QueueStatus.AVAILABLE:
            return PrintJobState.PRINTER_UNAVAILABLE
        details = self._run("lpstat", ("-l", "-o", job_id)).stdout
        state = _parse_job_state(details)
        if state is not PrintJobState.UNKNOWN:
            return state
        pending = self._run(
            "lpstat", ("-W", "not-completed", "-o", job_id)
        ).stdout
        if pending.strip():
            return PrintJobState.QUEUED
        completed = self._run("lpstat", ("-W", "completed", "-o", job_id)).stdout
        if completed.strip():
            return _parse_job_state(completed, default=PrintJobState.COMPLETED)
        return PrintJobState.UNKNOWN

    def _ensure_service(self) -> None:
        """Distinguish a stopped scheduler from an empty queue list."""
        result = self._run("lpstat", ("-r",))
        if "scheduler is running" not in result.stdout.casefold():
            raise PrintError("The CUPS service is unavailable.")

    def _require_cups_commands(self) -> str:
        """Resolve required CUPS executables before queue checks or USB discovery."""
        commands = ("lp", "lpstat", "lpoptions")
        resolved: dict[str, str] = {}
        for name in commands:
            command = self._runner.find_executable(name)
            if command is None:
                raise PrintError(f"The CUPS `{name}` command is unavailable.")
            resolved[name] = command
        return resolved["lp"]

    def _physical_printer_status(
        self,
    ) -> tuple[PhysicalPrinterStatus, str | None]:
        """Check lsusb output for the CP1000's observed vendor/product pair.

        The check is intentionally on-demand: submissions always call it, and
        protected Admin diagnostics call it only while the CUPS backend is
        selected. It never includes raw USB output in errors or logs.
        """
        command = self._runner.find_executable("lsusb")
        if command is None:
            _LOGGER.error("Physical printer USB check unavailable: lsusb is missing")
            return PhysicalPrinterStatus.UNKNOWN, "The `lsusb` command is unavailable."
        try:
            result = self._runner.run((command,), timeout=_COMMAND_TIMEOUT_SECONDS)
        except PrintProcessLaunchError:
            _LOGGER.error("Physical printer USB check could not start")
            return PhysicalPrinterStatus.UNKNOWN, "The `lsusb` command could not start."
        except PrintProcessTimeoutError:
            _LOGGER.error("Physical printer USB check timed out")
            return PhysicalPrinterStatus.UNKNOWN, "The USB printer check timed out."
        if result.returncode != 0:
            _LOGGER.error("Physical printer USB check failed with exit code %d", result.returncode)
            return PhysicalPrinterStatus.UNKNOWN, "The USB printer check failed."
        detected = _parse_lsusb_output(result.stdout)
        if detected is None:
            _LOGGER.error("Physical printer USB check returned unexpected output")
            return PhysicalPrinterStatus.UNKNOWN, "The USB printer check returned unexpected output."
        if detected:
            _LOGGER.info("Canon SELPHY CP1000 detected over USB")
            return PhysicalPrinterStatus.CONNECTED, None
        _LOGGER.warning("Canon SELPHY CP1000 not detected over USB")
        return PhysicalPrinterStatus.NOT_DETECTED, None

    def _queue_model(self, queue_name: str) -> str | None:
        """Read only the device URI host, discarding any serial or path portion."""
        output = self._run("lpstat", ("-v", queue_name)).stdout
        for line in output.splitlines():
            _, separator, uri = line.partition(":")
            if not separator:
                continue
            try:
                model = urlsplit(uri.strip()).hostname
            except ValueError:
                continue
            if model and re.fullmatch(r"[A-Za-z0-9._-]{1,160}", model):
                return model
        return None

    def _run(self, executable: str, arguments: tuple[str, ...]) -> _CommandOutput:
        """Resolve and run one CUPS command, translating failures for callers."""
        resolved = self._runner.find_executable(executable)
        if resolved is None:
            raise PrintError(f"The CUPS `{executable}` command is unavailable.")
        return self._run_command((resolved, *arguments), executable)

    def _run_command(
        self, arguments: tuple[str, ...] | list[str], executable: str
    ) -> _CommandOutput:
        """Run one finite argument list with a command-specific safe error."""
        try:
            result = self._runner.run(arguments, timeout=_COMMAND_TIMEOUT_SECONDS)
        except PrintProcessLaunchError as error:
            raise PrintError(f"The CUPS `{executable}` command could not start.") from error
        except PrintProcessTimeoutError as error:
            _LOGGER.error("CUPS %s command timed out", executable)
            raise PrintError(
                "The printer did not respond in time; check its queue before retrying.",
                uncertain=executable == "lp",
            ) from error
        if result.returncode != 0:
            _LOGGER.warning("CUPS %s command failed with exit code %d", executable, result.returncode)
            detail = f"{result.stdout}\n{result.stderr}".casefold()
            if executable == "lpstat" and (
                "scheduler is not running" in detail
                or "not responding" in detail
                or "unable to connect" in detail
                or "connection refused" in detail
            ):
                raise PrintError("The CUPS service is unavailable.")
            if executable == "lpoptions":
                raise PrintError("The configured printer capabilities are unavailable.")
            if executable == "lp":
                raise PrintError("The print request could not be submitted.")
            raise PrintError("CUPS could not report the configured printer status.")
        return _CommandOutput(result.returncode, result.stdout, result.stderr)


@dataclass(frozen=True)
class _CommandOutput:
    """Retain the typed output required for a small subset of CUPS parsing."""

    returncode: int
    stdout: str
    stderr: str


def _safe_queue_name(value: str) -> bool:
    """Return whether a discovered queue can safely occupy one argument."""
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}", value) is not None


def _parse_lsusb_output(output: str) -> bool | None:
    """Return CP1000 presence, or ``None`` if bounded lsusb output is malformed."""
    lines = tuple(line.strip() for line in output.splitlines() if line.strip())
    if not lines:
        return None
    detected = False
    for line in lines:
        match = _LSUSB_DEVICE_PATTERN.fullmatch(line)
        if match is None:
            return None
        if (
            match.group(1).casefold() == _CP1000_USB_VENDOR_ID
            and match.group(2).casefold() == _CP1000_USB_PRODUCT_ID
        ):
            detected = True
    return detected


def _validate_queue_name(value: str) -> None:
    """Reject queue names that could alter a command or identify an option."""
    if not _safe_queue_name(value):
        raise PrintError("The configured CUPS printer queue name is invalid.")


def _parse_options(output: str) -> dict[str, tuple[str, ...]]:
    """Parse only option identifiers and driver values from `lpoptions -l`."""
    options: dict[str, tuple[str, ...]] = {}
    for line in output.splitlines():
        name_and_label, separator, raw_values = line.partition(":")
        if not separator or "/" not in name_and_label:
            continue
        option_name = name_and_label.split("/", maxsplit=1)[0].strip()
        if not option_name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", option_name):
            continue
        values = tuple(
            value.removeprefix("*")
            for value in raw_values.split()
            if value.removeprefix("*")
        )
        options[option_name] = values
    return options


def _description(output: str) -> str | None:
    """Read a safe descriptive label without exposing interface paths or URIs."""
    for line in output.splitlines():
        key, separator, value = line.strip().partition(":")
        if separator and key.casefold() == "description" and value.strip():
            return value.strip()[:160]
    return None


def _is_jpeg(image_data: bytes) -> bool:
    """Verify that bytes decode as a JPEG instead of trusting a filename."""
    try:
        with Image.open(BytesIO(image_data)) as image:
            image.verify()
            return image.format == "JPEG"
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def _adjustment_option(value: int | None) -> str:
    """Map Python neutral to the queue's explicit driver value `None`."""
    return "None" if value is None else str(value)


def _parse_job_state(
    output: str, default: PrintJobState = PrintJobState.UNKNOWN
) -> PrintJobState:
    """Recognize CUPS state words without claiming a physical print occurred."""
    text = output.casefold()
    if "cancelled" in text or "canceled" in text:
        return PrintJobState.CANCELLED
    if "failed" in text or "aborted" in text:
        return PrintJobState.FAILED
    if "completed" in text or "completed successfully" in text:
        return PrintJobState.COMPLETED
    if any(word in text for word in ("pending", "processing", "held", "queued", "stopped")):
        return PrintJobState.QUEUED
    return default
