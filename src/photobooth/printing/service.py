"""Coordinate configured printer backends and prevent repeat CUPS submissions."""

from dataclasses import dataclass
import logging
from threading import Lock

from photobooth.printing.contract import (
    PrintError,
    PrintJobState,
    PrintResult,
    PrintStatus,
    PrinterUnavailableError,
    PrinterBackend,
)
from photobooth.printing.cups import CupsDiagnostics, CupsPrinterBackend
from photobooth.printing.null import NullPrinterBackend
from photobooth.printing.process import PrintProcessRunner
from photobooth.printing.settings import PrinterBackendKind, PrintingSettings

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrintingAdminDiagnostics:
    """Combine safe CUPS discovery with the most recent application print result."""

    cups: CupsDiagnostics
    effective_profile: dict[str, str]
    latest_result: PrintResult | None
    latest_job_state: PrintJobState
    latest_status_error: str | None
    last_submission_error: str | None


class PrintingService:
    """Select a backend, serialize CUPS jobs, and deduplicate by managed photo ID.

    Idempotency state is in memory for the lifetime of this service. A CUPS
    timeout or unparseable response is retained as uncertain so an accidental
    repeat does not submit another job; known failures may be retried. The
    application intentionally has no participant-facing reprint operation.
    """

    def __init__(
        self,
        settings: PrintingSettings,
        backend_override: PrinterBackend | None = None,
        process_runner: PrintProcessRunner | None = None,
    ) -> None:
        """Create a configured CUPS provider and select the active backend."""
        self._settings = settings
        self._backend_override = backend_override
        self._process_runner = process_runner
        self._lock = Lock()
        self._submitted: dict[str, PrintResult] = {}
        self._latest_result: PrintResult | None = None
        self._last_submission_error: str | None = None
        self._cups_backend = CupsPrinterBackend(settings, process_runner)
        self._active_backend = self._select_backend(settings)

    @property
    def active_backend_name(self) -> str:
        """Return the selected implementation name for protected diagnostics."""
        return type(self._active_backend).__name__

    def configure(self, settings: PrintingSettings) -> None:
        """Apply validated settings without discarding duplicate history."""
        with self._lock:
            self._settings = settings
            self._cups_backend = CupsPrinterBackend(settings, self._process_runner)
            self._active_backend = self._select_backend(settings)

    def validate_settings(self, settings: PrintingSettings) -> None:
        """Validate queue existence, availability, and selected driver values."""
        if settings.backend is PrinterBackendKind.CUPS:
            CupsPrinterBackend(settings, self._process_runner).validate_settings()

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Submit one managed image and block repeated requests for CUPS."""
        with self._lock:
            if not self._settings.enabled:
                raise PrintError("Printing is disabled in administration.")
            if self._settings.backend is not PrinterBackendKind.CUPS:
                return self._active_backend.print_photo(image_data, idempotency_key)
            previous = self._submitted.get(idempotency_key)
            if previous is not None:
                _LOGGER.warning("Blocked duplicate print request for a photo")
                if previous.status is PrintStatus.UNKNOWN:
                    self._latest_result = PrintResult(
                        status=PrintStatus.UNKNOWN,
                        queue_name=previous.queue_name,
                        status_text=(
                            "An earlier print request could not be confirmed; "
                            "check the queue before retrying."
                        ),
                    )
                    return self._latest_result
                self._latest_result = PrintResult(
                    status=PrintStatus.DUPLICATE,
                    queue_name=previous.queue_name,
                    job_id=previous.job_id,
                    submitted_at=previous.submitted_at,
                    status_text="This photo was already submitted to the printer.",
                )
                return self._latest_result
            try:
                result = self._active_backend.print_photo(image_data, idempotency_key)
            except PrinterUnavailableError as error:
                _LOGGER.warning("CUPS printer unavailable for submission: %s", error)
                result = PrintResult(
                    status=PrintStatus.UNAVAILABLE,
                    queue_name=self._settings.queue_name or None,
                    status_text="Imprimante indisponible.",
                )
                self._latest_result = result
                self._last_submission_error = str(error)[:200]
                return result
            except PrintError as error:
                if error.uncertain:
                    result = PrintResult(
                        status=PrintStatus.UNKNOWN,
                        queue_name=self._settings.queue_name or None,
                        status_text=str(error),
                    )
                    self._submitted[idempotency_key] = result
                    self._latest_result = result
                    self._last_submission_error = str(error)[:200]
                    return result
                self._last_submission_error = str(error)[:200]
                _LOGGER.warning("CUPS print submission failed: %s", self._last_submission_error)
                raise
            self._submitted[idempotency_key] = result
            self._latest_result = result
            self._last_submission_error = None
            return result

    def get_admin_diagnostics(self) -> PrintingAdminDiagnostics:
        """Return protected queue diagnostics and latest known job state."""
        cups = self._cups_backend.get_diagnostics()
        latest = self._latest_result
        latest_state = PrintJobState.UNKNOWN
        status_error: str | None = None
        if latest is not None and latest.job_id is not None:
            try:
                latest_state = self._cups_backend.get_job_status(latest.job_id)
            except PrintError as error:
                status_error = str(error)
                _LOGGER.warning("CUPS job status could not be refreshed: %s", status_error)
        profile = {
            "PageSize": self._settings.page_size.value,
            "ColorModel": self._settings.color_model.value,
            "Resolution": self._settings.resolution.value,
            "StpImageType": self._settings.image_type.value,
            "StpBorderless": str(self._settings.borderless),
            "StpiShrinkOutput": self._settings.page_fit.value,
            "StpColorPrecision": self._settings.color_precision.value,
            "StpColorCorrection": (
                "Par défaut / neutre"
                if self._settings.color_correction.value == "None"
                else self._settings.color_correction.value
            ),
            "StpLegacyDyesubGamma": str(self._settings.legacy_dyesub_gamma),
            "StpBrightness": _format_adjustment(self._settings.brightness),
            "StpContrast": _format_adjustment(self._settings.contrast),
            "StpSaturation": _format_adjustment(self._settings.saturation),
            "StpGamma": _format_adjustment(self._settings.gamma),
        }
        return PrintingAdminDiagnostics(
            cups=cups,
            effective_profile=profile,
            latest_result=latest,
            latest_job_state=latest_state,
            latest_status_error=status_error,
            last_submission_error=self._last_submission_error,
        )

    def _select_backend(self, settings: PrintingSettings) -> PrinterBackend:
        """Use an injected test backend or select CUPS/Null from configuration."""
        if self._backend_override is not None:
            return self._backend_override
        if settings.backend is PrinterBackendKind.CUPS:
            return self._cups_backend
        return NullPrinterBackend()


def _format_adjustment(value: int | None) -> str:
    """Show neutral settings distinctly from the Gutenprint literal `None`."""
    return "Par défaut / neutre" if value is None else str(value)
