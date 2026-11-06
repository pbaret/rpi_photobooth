"""Verify CUPS option validation, submission and duplicate handling without hardware."""

from collections.abc import Sequence
import base64
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image
import pytest

from photobooth.app import create_app
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import (
    ApplicationConfig,
    BoothSettings,
    StartupConfig,
    load_configuration,
    save_configuration,
)
from photobooth.printing.contract import PrintError, PrintJobState, PrintStatus
from photobooth.printing.cups import CupsPrinterBackend, QueueStatus
from photobooth.printing.process import (
    PrintCommandResult,
    PrintProcessTimeoutError,
)
from photobooth.printing.service import PrintingService
from photobooth.printing.settings import (
    PrintSettingsError,
    PrinterBackendKind,
    PrintingSettings,
    printing_settings_from_mapping,
)
from photobooth.services.preview import PreviewService

_CAPABILITIES = """\
PageSize/Media Size: *Postcard w253h337 w155h244
ColorModel/Color Model: Gray Black *RGB CMY CMYK KCMY
StpColorPrecision/Color Precision: *Normal Best
Resolution/Resolution: *300dpi
StpImageType/Image Type: None TextGraphics *Photo LineArt
StpiShrinkOutput/Shrink Page If Necessary to Fit Borders: *Shrink Crop Expand
StpBorderless/Borderless: *False True
StpLegacyDyesubGamma/Use legacy dyesub gamma curve: *False True
StpColorCorrection/Color Correction: *None Accurate Bright Hue Uncorrected Desaturated Threshold Density Raw Predithered
StpBrightness/Brightness: 0 100 200 300 400 500 600 700 800 900 *None 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 Custom.REAL
StpContrast/Contrast: 0 100 200 300 400 500 600 700 800 900 *None 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 Custom.REAL
StpSaturation/Saturation: 0 100 200 300 400 500 600 700 800 900 *None 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 5800 5900 6000 6100 6200 6300 6400 6500 6600 6700 6800 6900 7000 7100 7200 7300 7400 7500 7600 7700 7800 7900 8000 8100 8200 8300 8400 8500 8600 8700 8800 8900 9000 Custom.REAL
StpGamma/Composite Gamma: 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 *None Custom.REAL
"""


class FakePrintRunner:
    """Return deterministic CUPS command output while recording argument lists."""

    def __init__(self) -> None:
        """Start with an enabled CP1000 queue and the validated profile choices."""
        self.calls: list[tuple[str, ...]] = []
        self.queues: tuple[str, ...] = ("Canon_CP1000",)
        self.capabilities = _CAPABILITIES
        self.queue_enabled = True
        self.queue_accepting = True
        self.scheduler_output = "scheduler is running"
        self.job_details = ""
        self.pending_jobs = ""
        self.completed_jobs = ""
        self.lp_output = "request id is Canon_CP1000-42 (1 file(s))"
        self.lp_returncode = 0
        self.missing_executables: set[str] = set()
        self.timed_out_executables: set[str] = set()

    def find_executable(self, name: str) -> str | None:
        """Return a stable fake path unless the requested program is missing."""
        return None if name in self.missing_executables else f"/fake/{name}"

    def run(self, args: Sequence[str], timeout: float) -> PrintCommandResult:
        """Record one exact command and return its configured CUPS response."""
        del timeout
        command = Path(args[0]).name
        arguments = tuple(args[1:])
        self.calls.append(tuple(args))
        if command in self.timed_out_executables:
            raise PrintProcessTimeoutError("fake timeout")
        if command == "lp":
            if self.lp_returncode:
                return PrintCommandResult(self.lp_returncode, "", "bounded fake error")
            return PrintCommandResult(0, self.lp_output, "")
        if command == "lpstat":
            if arguments == ("-r",):
                return PrintCommandResult(0, self.scheduler_output, "")
            if arguments == ("-e",):
                return PrintCommandResult(0, "\n".join(self.queues), "")
            if arguments[:2] == ("-l", "-p"):
                enabled = "enabled since" if self.queue_enabled else "disabled since"
                output = f"printer {arguments[2]} is idle. {enabled} today\nDescription: Canon CP1000"
                return PrintCommandResult(0, output, "")
            if arguments[0] == "-a":
                accepting = "accepting requests" if self.queue_accepting else "not accepting requests"
                return PrintCommandResult(0, f"{arguments[1]} {accepting} today", "")
            if arguments[:1] == ("-v",):
                return PrintCommandResult(
                    0,
                    f"device for {arguments[1]}: gutenprint53+usb://canon-cp1000/private-serial",
                    "",
                )
            if arguments[:2] == ("-l", "-o"):
                return PrintCommandResult(0, self.job_details, "")
            if arguments[:2] == ("-W", "not-completed"):
                return PrintCommandResult(0, self.pending_jobs, "")
            if arguments[:2] == ("-W", "completed"):
                return PrintCommandResult(0, self.completed_jobs, "")
        if command == "lpoptions":
            return PrintCommandResult(0, self.capabilities, "")
        return PrintCommandResult(1, "", "unexpected fake command")


def _cups_settings(**overrides: object) -> PrintingSettings:
    """Build the default enabled CUPS configuration with selected changes."""
    settings = PrintingSettings(
        backend=PrinterBackendKind.CUPS,
        queue_name="Canon_CP1000",
    )
    return printing_settings_from_mapping(settings.to_mapping() | overrides)


def _jpeg_bytes() -> bytes:
    """Encode a tiny valid JPEG suitable for temporary-file submission tests."""
    image = Image.new("RGB", (8, 6), color=(20, 90, 150))
    data = BytesIO()
    image.save(data, format="JPEG")
    return data.getvalue()


def _calls_for(runner: FakePrintRunner, command: str) -> list[tuple[str, ...]]:
    """Filter recorded argument lists by their executable basename."""
    return [call for call in runner.calls if Path(call[0]).name == command]


def test_cp1000_defaults_map_to_reported_allowlisted_options() -> None:
    """The validated default profile maps each setting and sends explicit neutral values."""
    backend = CupsPrinterBackend(_cups_settings(), FakePrintRunner())

    assert backend.options_for_settings() == {
        "PageSize": "Postcard",
        "ColorModel": "RGB",
        "Resolution": "300dpi",
        "StpImageType": "Photo",
        "StpBorderless": "True",
        "StpiShrinkOutput": "Shrink",
        "StpColorPrecision": "Normal",
        "StpColorCorrection": "None",
        "StpLegacyDyesubGamma": "False",
        "StpBrightness": "None",
        "StpContrast": "None",
        "StpSaturation": "None",
        "StpGamma": "None",
    }


def test_supported_non_default_settings_are_validated_from_queue() -> None:
    """Discrete values advertised by the selected queue are accepted."""
    runner = FakePrintRunner()
    settings = _cups_settings(
        borderless=False,
        page_fit="Crop",
        color_precision="Best",
        color_correction="Accurate",
        brightness=100,
        contrast=200,
        saturation=300,
        gamma=400,
    )

    CupsPrinterBackend(settings, runner).validate_settings()


def test_queue_discovery_status_and_capability_parsing() -> None:
    """Diagnostics expose only discovered queue names, status, description and options."""
    runner = FakePrintRunner()
    backend = CupsPrinterBackend(_cups_settings(), runner)

    diagnostics = backend.get_diagnostics()

    assert diagnostics.queues == ("Canon_CP1000",)
    assert diagnostics.queue_status is QueueStatus.AVAILABLE
    assert diagnostics.queue_description == "Canon CP1000"
    assert diagnostics.queue_model == "canon-cp1000"
    assert "private-serial" not in repr(diagnostics)
    assert diagnostics.capabilities["StpGamma"][-1] == "Custom.REAL"
    assert "StpFineBrightness" not in diagnostics.capabilities


def test_empty_missing_disabled_and_unavailable_queues_are_distinguished() -> None:
    """Queue discovery distinguishes empty service, missing queue and disabled queue."""
    runner = FakePrintRunner()
    backend = CupsPrinterBackend(_cups_settings(), runner)
    runner.queues = ()
    assert backend.get_queue_status("Canon_CP1000")[0] is QueueStatus.NO_QUEUES
    runner.queues = ("Other",)
    assert backend.get_queue_status("Canon_CP1000")[0] is QueueStatus.NOT_FOUND
    runner.queues = ("Canon_CP1000",)
    runner.queue_enabled = False
    assert backend.get_queue_status("Canon_CP1000")[0] is QueueStatus.DISABLED
    runner.scheduler_output = "scheduler is not running"
    assert backend.get_diagnostics().error == "The CUPS service is unavailable."


def test_unsafe_queue_names_and_unsupported_settings_are_rejected() -> None:
    """Queue names and driver values cannot introduce unadvertised CUPS options."""
    with pytest.raises(PrintSettingsError, match="safe CUPS queue"):
        PrintingSettings(
            backend=PrinterBackendKind.CUPS,
            queue_name="queue -o Evil=True",
        )
    runner = FakePrintRunner()
    runner.capabilities = runner.capabilities.replace(
        "StpGamma/Composite Gamma:", "UnsupportedGamma/Composite Gamma:"
    )
    with pytest.raises(PrintError, match="does not support StpGamma"):
        CupsPrinterBackend(_cups_settings(), runner).validate_settings()
    with pytest.raises(PrintSettingsError, match="supported driver value"):
        _cups_settings(brightness=1000)


def test_admin_diagnostics_identify_stale_configured_driver_values() -> None:
    """Protected diagnostics name options that the current queue no longer supports."""
    runner = FakePrintRunner()
    runner.capabilities = runner.capabilities.replace(" 100 200 300", " 200 300", 1)

    diagnostics = CupsPrinterBackend(
        _cups_settings(brightness=100), runner
    ).get_diagnostics()

    assert diagnostics.unsupported_options == ("StpBrightness",)


def test_successful_submission_uses_managed_jpeg_and_exact_option_arguments() -> None:
    """CUPS receives a file-backed JPEG and one allowlisted option per argument pair."""
    runner = FakePrintRunner()
    result = CupsPrinterBackend(_cups_settings(), runner).print_photo(
        _jpeg_bytes(), "photo-identity"
    )

    lp_call = _calls_for(runner, "lp")[0]
    assert lp_call[1:3] == ("-d", "Canon_CP1000")
    assert lp_call[-1].endswith("/photo.jpg")
    assert result.status is PrintStatus.SUBMITTED
    assert result.queue_name == "Canon_CP1000"
    assert result.job_id == "Canon_CP1000-42"
    assert result.submitted_at is not None
    assert "-o" in lp_call
    assert "StpiShrinkOutput=Shrink" in lp_call
    assert "StpBrightness=None" in lp_call


def test_invalid_jpeg_and_disabled_queue_are_not_submitted() -> None:
    """A managed-photo corruption or disabled queue stops before invoking lp."""
    runner = FakePrintRunner()
    backend = CupsPrinterBackend(_cups_settings(), runner)
    with pytest.raises(PrintError, match="valid JPEG"):
        backend.print_photo(b"not an image", "photo-identity")
    assert not _calls_for(runner, "lp")

    runner.queue_accepting = False
    with pytest.raises(PrintError, match="unavailable"):
        backend.print_photo(_jpeg_bytes(), "photo-identity")
    assert not _calls_for(runner, "lp")


def test_missing_command_nonzero_exit_and_timeout_are_controlled() -> None:
    """CUPS launch, exit and timeout failures surface as typed safe errors."""
    runner = FakePrintRunner()
    runner.missing_executables.add("lp")
    with pytest.raises(PrintError, match="lp.*unavailable"):
        CupsPrinterBackend(_cups_settings(), runner).print_photo(
            _jpeg_bytes(), "photo-identity"
        )

    runner = FakePrintRunner()
    runner.lp_returncode = 1
    with pytest.raises(PrintError, match="could not be submitted") as submission_error:
        CupsPrinterBackend(_cups_settings(), runner).print_photo(
            _jpeg_bytes(), "photo-identity"
        )
    assert "bounded fake error" not in str(submission_error.value)

    runner = FakePrintRunner()
    runner.timed_out_executables.add("lp")
    with pytest.raises(PrintError) as timeout:
        CupsPrinterBackend(_cups_settings(), runner).print_photo(
            _jpeg_bytes(), "photo-identity"
        )
    assert timeout.value.uncertain


def test_missing_lpstat_and_lpoptions_are_reported() -> None:
    """Unavailable discovery and capability commands remain distinct diagnostics."""
    runner = FakePrintRunner()
    runner.missing_executables.add("lpstat")
    diagnostics = CupsPrinterBackend(_cups_settings(), runner).get_diagnostics()
    assert diagnostics.lpstat_available is False
    assert diagnostics.error == "The CUPS `lpstat` command is unavailable."

    runner = FakePrintRunner()
    runner.missing_executables.add("lpoptions")
    backend = CupsPrinterBackend(_cups_settings(), runner)
    with pytest.raises(PrintError, match="lpoptions.*unavailable"):
        backend.validate_settings()
    assert backend.get_diagnostics().error == "The CUPS `lpoptions` command is unavailable."


def test_unexpected_lp_output_is_uncertain_and_job_ids_are_not_guessed() -> None:
    """Unparseable successful output is not treated as a confirmed submission."""
    runner = FakePrintRunner()
    runner.lp_output = "job accepted without a request id"
    with pytest.raises(PrintError) as error:
        CupsPrinterBackend(_cups_settings(), runner).print_photo(
            _jpeg_bytes(), "photo-identity"
        )
    assert error.value.uncertain


def test_service_blocks_duplicate_and_allows_a_different_photo() -> None:
    """One photo cannot create a second CUPS job, while another photo can print."""
    runner = FakePrintRunner()
    service = PrintingService(_cups_settings(), process_runner=runner)

    first = service.print_photo(_jpeg_bytes(), "opaque-photo-one")
    duplicate = service.print_photo(_jpeg_bytes(), "opaque-photo-one")
    second = service.print_photo(_jpeg_bytes(), "opaque-photo-two")

    assert first.status is PrintStatus.SUBMITTED
    assert duplicate.status is PrintStatus.DUPLICATE
    assert duplicate.job_id == first.job_id
    assert second.status is PrintStatus.SUBMITTED
    assert len(_calls_for(runner, "lp")) == 2


def test_uncertain_timeout_is_retained_and_prevents_repeated_submit() -> None:
    """An ambiguous timeout is never silently retried for the same photo."""
    runner = FakePrintRunner()
    runner.timed_out_executables.add("lp")
    service = PrintingService(_cups_settings(), process_runner=runner)

    uncertain = service.print_photo(_jpeg_bytes(), "opaque-photo-one")
    duplicate = service.print_photo(_jpeg_bytes(), "opaque-photo-one")

    assert uncertain.status is PrintStatus.UNKNOWN
    assert duplicate.status is PrintStatus.UNKNOWN
    assert len(_calls_for(runner, "lp")) == 1


@pytest.mark.parametrize(
    ("details", "pending", "completed", "expected"),
    [
        ("job-state: processing", "", "", PrintJobState.QUEUED),
        ("job-state: completed", "", "", PrintJobState.COMPLETED),
        ("job-state: aborted", "", "", PrintJobState.FAILED),
        ("job-state: canceled", "", "", PrintJobState.CANCELLED),
        ("", "", "Canon_CP1000-42 owner 1 1", PrintJobState.COMPLETED),
        ("", "", "", PrintJobState.UNKNOWN),
    ],
)
def test_cups_job_state_mapping(
    details: str,
    pending: str,
    completed: str,
    expected: PrintJobState,
) -> None:
    """Available CUPS state output is mapped without asserting physical success."""
    runner = FakePrintRunner()
    runner.job_details = details
    runner.pending_jobs = pending
    runner.completed_jobs = completed

    state = CupsPrinterBackend(_cups_settings(), runner).get_job_status(
        "Canon_CP1000-42"
    )

    assert state is expected


def test_job_status_reports_printer_unavailable_and_unknown_ids() -> None:
    """A queue outage or foreign job identifier cannot be mislabeled as complete."""
    runner = FakePrintRunner()
    backend = CupsPrinterBackend(_cups_settings(), runner)

    assert backend.get_job_status("Other-1") is PrintJobState.UNKNOWN
    runner.queue_enabled = False
    assert backend.get_job_status("Canon_CP1000-42") is PrintJobState.PRINTER_UNAVAILABLE


def test_disabled_printing_and_disabled_null_backend_are_honored() -> None:
    """Application-level printing enablement blocks even the development no-op."""
    settings = PrintingSettings(enabled=False)
    service = PrintingService(settings)

    with pytest.raises(PrintError, match="disabled"):
        service.print_photo(_jpeg_bytes(), "opaque-photo-one")


def test_legacy_configuration_defaults_and_new_profile_round_trip(
    tmp_path: Path,
) -> None:
    """Older configuration documents load defaults and serialize print settings."""
    config_path = tmp_path / "config.json"
    config_path.write_text('{"startup": {}, "booth": {}}', encoding="utf-8")

    older = load_configuration(config_path)

    assert older.printing == PrintingSettings()
    updated = ApplicationConfig(
        older.startup,
        older.booth,
        config_path,
        printing=_cups_settings(brightness=100),
    )
    save_configuration(updated)

    assert load_configuration(config_path).printing == _cups_settings(brightness=100)


def test_null_backend_never_invokes_cups() -> None:
    """The development printer remains a no-op even when CUPS is available."""
    runner = FakePrintRunner()
    service = PrintingService(PrintingSettings(), process_runner=runner)

    result = service.print_photo(_jpeg_bytes(), "opaque-photo-one")

    assert result.status is PrintStatus.PLACEHOLDER
    assert runner.calls == []


def test_disabled_printing_disables_review_control(tmp_path: Path) -> None:
    """A disabled printing setting keeps the photo in review with a disabled action."""
    settings = PrintingSettings(enabled=False)
    configuration = ApplicationConfig(
        startup=StartupConfig(data_root=tmp_path / "data"),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
        printing=settings,
    )
    app = create_app(configuration=configuration, camera_backend=SyntheticCameraBackend())
    client = app.test_client()
    capture = client.post("/capture")
    assert capture.status_code == 200
    payload = capture.get_json()
    assert isinstance(payload, dict)
    review_path = cast(dict[str, object], payload).get("review_url")
    assert isinstance(review_path, str)

    review = client.get(review_path)

    assert b"L'impression est d\xc3\xa9sactiv\xc3\xa9e sur cet appareil." in review.data
    assert b'id="print-button"' in review.data
    assert b"disabled>Imprimer</button>" in review.data
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    preview.close()


def test_admin_renders_live_queue_choices_without_exposing_driver_extras(
    tmp_path: Path,
) -> None:
    """Protected admin reads queue options but exposes no CMY or fine controls."""
    runner = FakePrintRunner()
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret="admin-secret",
        ),
        booth=BoothSettings(),
        config_path=tmp_path / "config.json",
        printing=_cups_settings(),
    )
    app = create_app(configuration=configuration, print_process_runner=runner)
    credential = base64.b64encode(b"admin:admin-secret").decode("ascii")

    response = app.test_client().get(
        "/admin", headers={"Authorization": f"Basic {credential}"}
    )

    assert response.status_code == 200
    assert b"Canon_CP1000" in response.data
    assert b"canon-cp1000" in response.data
    assert b"available" in response.data
    assert (
        b'<option value="None" selected>Par d\xc3\xa9faut / neutre</option>'
        in response.data
    )
    assert b"StpFine" not in response.data
    assert b"Cyan" not in response.data
    assert b"Custom.REAL" not in response.data
    assert not _calls_for(runner, "lp")
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    preview.close()


def test_review_route_keeps_photo_and_blocks_repeated_cups_submission(
    tmp_path: Path,
) -> None:
    """Repeated REVIEW POSTs reuse the job result and never launch a second lp."""
    runner = FakePrintRunner()
    configuration = ApplicationConfig(
        startup=StartupConfig(data_root=tmp_path / "data"),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
        printing=_cups_settings(),
    )
    app = create_app(
        configuration=configuration,
        camera_backend=SyntheticCameraBackend(),
        print_process_runner=runner,
    )
    client = app.test_client()
    capture = client.post("/capture")
    assert capture.status_code == 200
    payload = capture.get_json()
    assert isinstance(payload, dict)
    review_path = cast(dict[str, object], payload).get("review_url")
    assert isinstance(review_path, str)
    photo_id = review_path.rsplit("/", maxsplit=1)[-1]

    submitted = client.post(f"/review/{photo_id}/print")
    repeated = client.post(f"/review/{photo_id}/print")

    assert submitted.status_code == 303
    assert repeated.status_code == 303
    assert f"/review/{photo_id}?print_status=duplicate" in repeated.headers["Location"]
    review = client.get(repeated.headers["Location"])
    assert review.status_code == 200
    assert b"Cette photo a d\xc3\xa9j\xc3\xa0 \xc3\xa9t\xc3\xa9 envoy\xc3\xa9e" in review.data
    assert len(_calls_for(runner, "lp")) == 1
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    preview.close()


def test_real_process_runner_reports_bounded_command_output() -> None:
    """The finite runner executes a command with captured bounded standard output."""
    import sys

    from photobooth.printing.process import SubprocessPrintProcessRunner

    result = SubprocessPrintProcessRunner().run(
        (
            sys.executable,
            "-c",
            "import sys; print('x' * 70000); sys.stderr.write('e' * 70000)",
        ),
        timeout=5.0,
    )

    assert result.returncode == 0
    assert len(result.stdout) <= 64 * 1024
    assert len(result.stderr) <= 64 * 1024
