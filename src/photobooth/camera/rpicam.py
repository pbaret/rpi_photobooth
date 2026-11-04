"""Implement CameraBackend with the Raspberry Pi rpicam-apps executables.

Version 1 drives the operating-system ``rpicam-vid`` and ``rpicam-still``
programs through the typed process boundary in
:mod:`photobooth.camera.process`. ``rpicam-vid`` is a long-lived MJPEG preview
child that owns the camera while preview is active; ``rpicam-still`` is a finite
child that performs high-resolution capture after preview is confirmed stopped.

Preview is started lazily by the first ``preview_frame`` call rather than by
``start``. The application's preview service calls ``start`` immediately before
``capture``, so spawning ``rpicam-vid`` there would only be torn down again
before the still is taken.

Application code only sees the camera contract. Command lines are built from an
explicit allowlist of settings; no request, configuration string or form value
is ever passed through as a command-line argument.
"""

import logging
import os
import secrets
import shlex
from collections.abc import Mapping
from pathlib import Path
from threading import Condition, Lock, Thread
from typing import Final

from PIL import Image, UnidentifiedImageError

from photobooth.camera.contract import CameraOperationError, CameraUnavailableError
from photobooth.camera.mjpeg import MjpegFrameParser
from photobooth.camera.process import (
    CameraProcessRunner,
    LongRunningProcess,
    ProcessLaunchError,
    ProcessTimeoutError,
    SubprocessCameraProcessRunner,
)
from photobooth.camera.rpicam_settings import (
    JPEG_QUALITY_MAXIMUM,
    JPEG_QUALITY_MINIMUM,
    PREVIEW_SIZES,
    RpicamSettings,
    capabilities_for,
    format_number,
    settings_from_mapping,
)
from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingValue,
    ValidatedCameraSetting,
    validate_camera_setting,
)

__all__ = [
    "JPEG_QUALITY_MAXIMUM",
    "JPEG_QUALITY_MINIMUM",
    "PREVIEW_SIZES",
    "RpicamCameraBackend",
    "RpicamSettings",
    "build_preview_command",
    "build_still_command",
]

_LOGGER = logging.getLogger(__name__)

_VID_EXECUTABLE: Final = "rpicam-vid"
_STILL_EXECUTABLE: Final = "rpicam-still"
_READ_CHUNK_BYTES: Final = 65536
_READER_JOIN_SECONDS: Final = 2.0
_OUTPUT_PLACEHOLDER: Final = "<temporary-output>"


def build_preview_command(executable: str, settings: RpicamSettings) -> tuple[str, ...]:
    """Build the argument list for an indefinite MJPEG preview on stdout.

    ``-t 0`` disables rpicam-vid's default five-second run limit. ``--flush``
    asks for each frame to be written as soon as it is encoded.
    """
    width, height = settings.preview_dimensions
    return (
        executable,
        "--nopreview",
        "-t",
        "0",
        "--codec",
        "mjpeg",
        "--width",
        str(width),
        "--height",
        str(height),
        "--awb",
        settings.white_balance.value,
        "--flush",
        "-o",
        "-",
    )


def build_still_command(
    executable: str, settings: RpicamSettings, output_path: Path
) -> tuple[str, ...]:
    """Build the argument list for one JPEG still from validated settings.

    Every argument comes from a typed field, never from free text. Inactive
    settings are omitted rather than emitted with placeholder values:

    - ``--shutter`` and ``--gain`` only appear in manual exposure; automatic
      exposure leaves both to the AE algorithm.
    - Manual focus emits ``--lens-position`` and no autofocus range, speed,
      window or on-capture argument; automatic and continuous focus emit
      those instead and never a lens position.
    - ``--immediate`` skips rpicam-still's viewfinder phase. rpicam-apps 1.14
      only runs the ``--autofocus-on-capture`` scan during that phase, so
      ``--immediate`` is dropped whenever the scan is requested (verified on
      Camera Module 3: with ``--immediate`` the lens did not move).

    Options with an implicit value (``--hdr``, ``--verbose``) use the
    ``--option=value`` form so the value cannot be parsed as a separate
    token. Raises ``ValueError`` if cross-field rules fail.
    """
    settings.validate()
    command: list[str] = [executable, "--nopreview"]
    if not settings.scans_on_capture:
        command.append("--immediate")
    command += [
        "-t",
        "1",
        "--encoding",
        "jpg",
        "--quality",
        str(settings.jpeg_quality),
        "--width",
        str(settings.still_width),
        "--height",
        str(settings.still_height),
        "--awb",
        settings.white_balance.value,
        "--metering",
        settings.metering.value,
        "--exposure",
        settings.exposure_mode.value,
        "--ev",
        format_number(settings.ev),
    ]
    if settings.manual_exposure:
        command += [
            "--shutter",
            str(settings.shutter_us),
            "--gain",
            format_number(settings.gain),
        ]
    command += [
        "--brightness",
        format_number(settings.brightness),
        "--contrast",
        format_number(settings.contrast),
        "--saturation",
        format_number(settings.saturation),
        "--sharpness",
        format_number(settings.sharpness),
        "--denoise",
        settings.denoise.value,
        f"--hdr={settings.hdr.value}",
        "--autofocus-mode",
        settings.autofocus_mode.value,
    ]
    if settings.manual_focus:
        command += ["--lens-position", format_number(settings.lens_position)]
    else:
        command += [
            "--autofocus-range",
            settings.autofocus_range.value,
            "--autofocus-speed",
            settings.autofocus_speed.value,
            "--autofocus-window",
            settings.autofocus_window.to_argument(),
        ]
        if settings.scans_on_capture:
            command.append("--autofocus-on-capture")
    command += [f"--verbose={settings.verbosity}", "-o", str(output_path)]
    return tuple(command)


class _PreviewEndedError(Exception):
    """Internal signal that rpicam-vid stopped producing output."""


class _PreviewSession:
    """Own one rpicam-vid process and the thread that turns its stdout into frames.

    The reader thread stores only the newest complete frame and bumps a
    generation counter. ``next_frame`` hands out each generation at most once,
    so a slow browser cannot make the backend return stale duplicates. Instances
    are created and closed under the backend lock; the condition variable only
    coordinates the reader thread with the caller waiting for a frame.
    """

    def __init__(self, process: LongRunningProcess) -> None:
        """Wrap a started process; call ``start`` to begin reading its output."""
        self.process = process
        self._parser = MjpegFrameParser()
        self._condition = Condition()
        self._latest: bytes | None = None
        self._generation = 0
        self._returned_generation = 0
        self._finished = False
        self._reader = Thread(target=self._read_frames, name="rpicam-vid-reader", daemon=True)

    @property
    def returned_generation(self) -> int:
        """Return how many frames have been handed to the preview caller so far."""
        with self._condition:
            return self._returned_generation

    def start(self) -> None:
        """Begin consuming stdout on the reader thread."""
        self._reader.start()

    def next_frame(self, timeout: float) -> bytes | None:
        """Wait up to ``timeout`` seconds for a frame not yet handed out.

        Returns ``None`` on timeout. Raises ``_PreviewEndedError`` once the
        process output has ended and no undelivered frame remains.
        """
        with self._condition:
            self._condition.wait_for(
                lambda: self._generation > self._returned_generation or self._finished,
                timeout,
            )
            frame = self._latest
            if frame is not None and self._generation > self._returned_generation:
                self._returned_generation = self._generation
                return frame
            if self._finished:
                raise _PreviewEndedError("rpicam-vid output ended")
            return None

    def close(self) -> None:
        """Wait for the reader to observe EOF, then release the process pipes.

        Must only be called after the process has exited, so the reader is
        guaranteed to reach EOF and the join is bounded.
        """
        self._reader.join(_READER_JOIN_SECONDS)
        if self._reader.is_alive():
            _LOGGER.warning("rpicam-vid reader did not finish; pipes left open")
            return
        self.process.close()

    def _read_frames(self) -> None:
        """Parse stdout into frames until EOF or a read failure, then mark the session finished."""
        try:
            while True:
                chunk = self.process.read_output(_READ_CHUNK_BYTES)
                if not chunk:
                    return
                frames = self._parser.feed(chunk)
                if frames:
                    with self._condition:
                        self._latest = frames[-1]
                        self._generation += 1
                        self._condition.notify_all()
        finally:
            with self._condition:
                self._finished = True
                self._condition.notify_all()


class RpicamCameraBackend:
    """Provide preview and still capture from a Raspberry Pi camera via rpicam-apps.

    Lifecycle: ``start`` validates that the executables exist and marks the
    backend ready. The first ``preview_frame`` after start spawns ``rpicam-vid``;
    later calls return successive frames from it. ``capture`` terminates
    ``rpicam-vid`` (waiting for exit), runs ``rpicam-still`` with a timeout into
    a temporary file, validates the JPEG, publishes it to the caller's path with
    an atomic replace, and leaves the backend stopped.

    Settings are stored when configured and take effect on the next launched
    command. ``preview_size`` requires a restart and therefore cannot be applied
    to a running backend.

    Thread safety: every public method holds one lock for its full duration, so
    a blocked ``preview_frame`` delays concurrent ``stop`` calls. Owned child
    processes are never left running after a successful ``stop``. If a child
    cannot be terminated, ``stop`` raises ``CameraOperationError`` and keeps
    ownership so it can be retried; a SIGKILLed Python parent cannot clean up
    its children, which is a documented limitation.
    """

    def __init__(
        self,
        runner: CameraProcessRunner | None = None,
        *,
        startup_timeout_seconds: float = 10.0,
        frame_timeout_seconds: float = 3.0,
        stop_timeout_seconds: float = 3.0,
        still_timeout_seconds: float = 30.0,
    ) -> None:
        """Create a stopped backend that will use ``runner`` for every child process.

        The default runner is the operating-system subprocess implementation.
        Timeouts bound first-frame wait, steady-state frame wait, each graceful
        or forceful termination wait, and the finite still command.
        """
        self._runner: CameraProcessRunner = (
            runner if runner is not None else SubprocessCameraProcessRunner()
        )
        self._startup_timeout = startup_timeout_seconds
        self._frame_timeout = frame_timeout_seconds
        self._stop_timeout = stop_timeout_seconds
        self._still_timeout = still_timeout_seconds
        self._lock = Lock()
        self._settings = RpicamSettings()
        self._last_still_command: str | None = None
        self._started = False
        self._preview: _PreviewSession | None = None

    def get_capabilities(self) -> tuple[CameraSettingCapability, ...]:
        """Declare the allowlisted rpicam settings and their current requested values."""
        with self._lock:
            return self._capabilities_locked()

    def configure_settings(self, settings: Mapping[str, CameraSettingValue]) -> None:
        """Load persisted requests for known settings; unknown keys are ignored.

        The whole mapping is applied atomically: invalid, read-only or
        mutually inconsistent values raise ``ValueError`` and leave every
        previously stored setting unchanged.
        """
        with self._lock:
            self._settings = settings_from_mapping(self._settings, settings)

    def validate_settings(self, settings: Mapping[str, CameraSettingValue]) -> None:
        """Check a complete requested set over the defaults without storing it.

        Enforces per-setting bounds and cross-setting rules such as the
        autofocus window staying inside the frame. Raises ``ValueError``
        starting with the offending identifier.
        """
        settings_from_mapping(RpicamSettings(), settings)

    def apply_setting(self, setting: ValidatedCameraSetting) -> CameraSettingValue:
        """Apply a runtime-changeable setting to the next launched command.

        Raises ``ValueError`` for unknown, read-only or restart-required
        settings, and for values outside the declared allowlist. Cross-field
        rules are not checked here because a multi-field update applies one
        setting at a time; callers check the final set with
        ``validate_settings`` first, and still-command construction re-checks.
        """
        with self._lock:
            capabilities = {item.identifier: item for item in self._capabilities_locked()}
            capability = capabilities.get(setting.identifier)
            if capability is None:
                raise ValueError(f"{setting.identifier} is unsupported")
            if capability.read_only or capability.restart_required:
                raise ValueError(f"{setting.identifier} cannot be applied without restart")
            validated = validate_camera_setting(capability, setting.value)
            self._store_setting_locked(validated)
            return validated.value

    def start(self) -> None:
        """Mark the backend ready after confirming both rpicam executables are installed.

        Repeated calls while started are no-ops. Raises ``CameraUnavailableError``
        and leaves the backend stopped if an executable is missing.
        """
        with self._lock:
            if self._started:
                return
            self._resolve_executable_locked(_VID_EXECUTABLE)
            self._resolve_executable_locked(_STILL_EXECUTABLE)
            self._started = True

    def stop(self) -> None:
        """Terminate any live preview process and leave the backend stopped.

        Repeated calls are harmless. If the preview process cannot be terminated,
        ``CameraOperationError`` is raised and the backend remains started so the
        caller can retry.
        """
        with self._lock:
            if not self._started:
                return
            self._stop_preview_locked()
            self._started = False

    def preview_frame(self) -> bytes:
        """Return the next JPEG preview frame, spawning rpicam-vid on first use.

        The first frame may take up to the startup timeout; later frames use the
        frame timeout. A failure stops the backend before the error is raised.
        Raises ``CameraUnavailableError`` if the backend is stopped or preview
        cannot start, and ``CameraOperationError`` if preview fails afterwards.
        """
        with self._lock:
            self._require_started_locked()
            first_frame = self._preview is None or self._preview.returned_generation == 0
            try:
                session = self._ensure_preview_locked()
                frame = session.next_frame(
                    self._startup_timeout if first_frame else self._frame_timeout
                )
            except _PreviewEndedError as error:
                self._abandon_preview_locked()
                if first_frame:
                    raise CameraUnavailableError(
                        "rpicam-vid exited before producing a preview frame"
                    ) from error
                raise CameraOperationError("rpicam-vid stopped during preview") from error
            except CameraUnavailableError:
                self._abandon_preview_locked()
                raise
            if frame is None:
                self._abandon_preview_locked()
                if first_frame:
                    raise CameraUnavailableError("rpicam-vid produced no preview frame in time")
                raise CameraOperationError("rpicam-vid preview frame timed out")
            return frame

    def capture(self, output_path: Path) -> None:
        """Capture one still into ``output_path`` and leave the backend stopped.

        Preview is stopped and confirmed terminated before ``rpicam-still`` runs.
        The JPEG is written beside ``output_path`` and published with an atomic
        replace only after it validates. Failed captures leave no file at
        ``output_path``. Raises ``CameraUnavailableError`` if the backend is not
        started, and ``CameraOperationError`` if preview cannot be stopped or
        the still fails.
        """
        with self._lock:
            self._require_started_locked()
            self._stop_preview_locked()
            try:
                self._run_still_locked(output_path)
            finally:
                self._started = False

    def _capabilities_locked(self) -> tuple[CameraSettingCapability, ...]:
        """Build the declared settings from the current requested values."""
        return capabilities_for(self._settings, self._last_still_command)

    def _store_setting_locked(self, setting: ValidatedCameraSetting) -> None:
        """Replace one allowlisted option after its value has been validated."""
        self._settings = self._settings.with_setting(setting)

    def _require_started_locked(self) -> None:
        """Raise ``CameraUnavailableError`` unless ``start`` has succeeded."""
        if not self._started:
            raise CameraUnavailableError("camera is not started")

    def _resolve_executable_locked(self, name: str) -> str:
        """Return the executable path for ``name`` or report it as unavailable."""
        path = self._runner.find_executable(name)
        if path is None:
            raise CameraUnavailableError(f"{name} is not installed or not on PATH")
        return path

    def _ensure_preview_locked(self) -> _PreviewSession:
        """Return the live preview session, spawning rpicam-vid if none exists."""
        if self._preview is not None:
            return self._preview
        executable = self._resolve_executable_locked(_VID_EXECUTABLE)
        args = build_preview_command(executable, self._settings)
        try:
            process = self._runner.start(args)
        except ProcessLaunchError as error:
            raise CameraUnavailableError("rpicam-vid could not be started") from error
        session = _PreviewSession(process)
        self._preview = session
        session.start()
        return session

    def _stop_preview_locked(self) -> None:
        """Terminate rpicam-vid: SIGINT, wait, SIGKILL if needed, wait again.

        The session is retained if the process cannot be confirmed terminated,
        so a later stop or capture can retry instead of losing track of it.
        """
        session = self._preview
        if session is None:
            return
        process = session.process
        if process.poll() is None:
            process.interrupt()
            if process.wait(self._stop_timeout) is None:
                _LOGGER.warning("rpicam-vid ignored SIGINT; killing it")
                process.kill()
                if process.wait(self._stop_timeout) is None:
                    raise CameraOperationError("rpicam-vid could not be terminated")
        session.close()
        self._preview = None

    def _abandon_preview_locked(self) -> None:
        """Stop the backend after a preview failure, keeping ownership if cleanup fails."""
        session = self._preview
        if session is not None:
            _LOGGER.warning(
                "rpicam-vid preview failed: %s", session.process.stderr_tail() or "no stderr"
            )
        try:
            self._stop_preview_locked()
        except CameraOperationError:
            _LOGGER.exception("rpicam-vid cleanup failed; backend remains started for retry")
            return
        self._started = False

    def _run_still_locked(self, output_path: Path) -> None:
        """Run rpicam-still into a sibling temporary file and publish it atomically.

        The exact argument list is logged at INFO with ``shlex.join`` just
        before execution; the logged text is never executed. The runner still
        receives the original argument sequence and never uses a shell. The
        arguments and outcome are kept for the read-only diagnostic setting,
        with the temporary output path replaced by a placeholder.
        """
        executable = self._resolve_executable_locked(_STILL_EXECUTABLE)
        temporary = output_path.with_name(
            f".{output_path.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            args = build_still_command(executable, self._settings, temporary)
        except ValueError as error:
            raise CameraOperationError("rpicam still settings are inconsistent") from error
        display = shlex.join((*args[:-1], _OUTPUT_PLACEHOLDER))
        _LOGGER.info("Running rpicam-still: %s", shlex.join(args))
        try:
            try:
                result = self._runner.run(args, self._still_timeout)
            except ProcessLaunchError as error:
                self._last_still_command = f"{display} (could not start)"
                raise CameraUnavailableError("rpicam-still could not be started") from error
            except ProcessTimeoutError as error:
                self._last_still_command = f"{display} (timed out)"
                raise CameraOperationError("rpicam-still timed out") from error
            self._last_still_command = f"{display} (exit {result.returncode})"
            if result.returncode != 0:
                _LOGGER.warning("rpicam-still exited %d: %s", result.returncode, result.stderr_tail)
                raise CameraOperationError("rpicam-still failed")
            _validate_jpeg(temporary)
            os.replace(temporary, output_path)
        except OSError as error:
            raise CameraOperationError("capture output could not be published") from error
        finally:
            temporary.unlink(missing_ok=True)


def _validate_jpeg(path: Path) -> None:
    """Require a non-empty file that Pillow identifies as a complete JPEG image."""
    try:
        if path.stat().st_size == 0:
            raise ValueError("still output is empty")
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise ValueError("still output is not a JPEG")
            image.verify()
    except (OSError, SyntaxError, ValueError, UnidentifiedImageError) as error:
        raise CameraOperationError("rpicam-still did not produce a valid JPEG") from error
