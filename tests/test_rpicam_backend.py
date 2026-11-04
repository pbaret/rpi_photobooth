"""Verify rpicam backend lifecycle, command construction and capture publication.

All child processes are replaced by typed fakes at the ``CameraProcessRunner``
boundary, so these tests never require rpicam, a camera or Raspberry Pi
hardware. Timeouts are set to tiny values so frame and stop waits end quickly
without real sleeps.
"""

import io
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from photobooth.camera.contract import CameraOperationError, CameraUnavailableError
from photobooth.camera.process import (
    FiniteCommandResult,
    ProcessLaunchError,
    ProcessTimeoutError,
)
from photobooth.camera.rpicam import (
    RpicamCameraBackend,
    RpicamSettings,
    build_preview_command,
    build_still_command,
)
from photobooth.camera.settings import validate_camera_setting

VID_PATH = "/usr/bin/rpicam-vid"
STILL_PATH = "/usr/bin/rpicam-still"
FRAME_ONE = b"\xff\xd8\x01\xff\xd9"
FRAME_TWO = b"\xff\xd8\x02\xff\xd9"


def make_jpeg() -> bytes:
    """Return a small valid JPEG image encoded with Pillow."""
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeProcess:
    """Stand-in for a long-running rpicam-vid process with scripted stdout.

    Frames are delivered in order. Once they are exhausted, reads block until
    the process exits, mirroring a live pipe. ``ignore_interrupt`` and
    ``ignore_kill`` simulate a child that refuses termination.
    """

    def __init__(
        self,
        frames: Sequence[bytes] = (),
        *,
        exit_code: int | None = None,
        ignore_interrupt: bool = False,
        ignore_kill: bool = False,
    ) -> None:
        """Script stdout chunks and optional immediate exit status."""
        self._chunks: deque[bytes] = deque(frames)
        self._exit_code = exit_code
        self._eof = Event()
        if exit_code is not None:
            self._eof.set()
        self.ignore_interrupt = ignore_interrupt
        self.ignore_kill = ignore_kill
        self.interrupts = 0
        self.kills = 0
        self.closed = False

    def read_output(self, size: int) -> bytes:
        """Return the next scripted chunk, or block until exit and return EOF."""
        if self._chunks:
            return self._chunks.popleft()
        self._eof.wait()
        return b""

    def poll(self) -> int | None:
        """Return the scripted exit code once the process has exited."""
        return self._exit_code

    def interrupt(self) -> None:
        """Record SIGINT and exit unless configured to ignore it."""
        self.interrupts += 1
        if not self.ignore_interrupt:
            self._exit(0)

    def kill(self) -> None:
        """Record SIGKILL and exit unless configured to ignore it."""
        self.kills += 1
        if not self.ignore_kill:
            self._exit(-9)

    def wait(self, timeout: float) -> int | None:
        """Report the exit code without blocking; ``None`` means still running."""
        return self._exit_code

    def stderr_tail(self) -> str:
        """Return no diagnostic text."""
        return ""

    def close(self) -> None:
        """Record that stdout and stderr were released."""
        self.closed = True

    def end(self, exit_code: int) -> None:
        """Simulate the process exiting on its own with ``exit_code``."""
        self._exit(exit_code)

    def _exit(self, exit_code: int) -> None:
        """Mark the process exited and unblock any pending stdout read."""
        if self._exit_code is None:
            self._exit_code = exit_code
            self._eof.set()


class FakeRunner:
    """Record every launched command and supply scripted processes and results."""

    def __init__(
        self,
        *,
        vid: str | None = VID_PATH,
        still: str | None = STILL_PATH,
    ) -> None:
        """Map executable names to resolved paths; ``None`` simulates a missing binary."""
        self._paths: dict[str, str | None] = {"rpicam-vid": vid, "rpicam-still": still}
        self.processes: list[FakeProcess] = []
        self.next_process: Callable[[], FakeProcess] = FakeProcess
        self.start_args: list[tuple[str, ...]] = []
        self.run_args: list[tuple[str, ...]] = []
        self.run_handler: Callable[[tuple[str, ...], float], FiniteCommandResult] = (
            write_jpeg_still()
        )
        self.start_error: ProcessLaunchError | None = None

    def find_executable(self, name: str) -> str | None:
        """Return the scripted path for ``name``."""
        return self._paths.get(name)

    def start(self, args: Sequence[str]) -> FakeProcess:
        """Record the command and return the next scripted process."""
        if self.start_error is not None:
            raise self.start_error
        self.start_args.append(tuple(args))
        process = self.next_process()
        self.processes.append(process)
        return process

    def run(self, args: Sequence[str], timeout: float) -> FiniteCommandResult:
        """Record the finite command and delegate to the scripted handler."""
        command = tuple(args)
        self.run_args.append(command)
        return self.run_handler(command, timeout)


def write_jpeg_still(
    *, returncode: int = 0, payload: bytes | None = None
) -> Callable[[tuple[str, ...], float], FiniteCommandResult]:
    """Build a still handler that writes ``payload`` to the ``-o`` path it is given."""

    def handler(args: tuple[str, ...], timeout: float) -> FiniteCommandResult:
        """Write the scripted bytes to the temporary output path in ``args``."""
        output = Path(args[-1])
        output.write_bytes(payload if payload is not None else make_jpeg())
        return FiniteCommandResult(returncode=returncode, stderr_tail="")

    return handler


def make_backend(runner: FakeRunner) -> RpicamCameraBackend:
    """Create a backend whose waits end immediately in tests."""
    return RpicamCameraBackend(
        runner,
        startup_timeout_seconds=0.05,
        frame_timeout_seconds=0.05,
        stop_timeout_seconds=0.05,
        still_timeout_seconds=1.0,
    )


def test_missing_executable_fails_start_and_leaves_backend_stopped() -> None:
    backend = make_backend(FakeRunner(vid=None))

    with pytest.raises(CameraUnavailableError):
        backend.start()
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_start_validates_executables_without_spawning_preview() -> None:
    runner = FakeRunner()
    backend = make_backend(runner)

    backend.start()

    assert runner.start_args == []


def test_first_preview_frame_spawns_rpicam_vid_with_exact_arguments() -> None:
    runner = FakeRunner()
    runner.next_process = lambda: FakeProcess([FRAME_ONE])
    backend = make_backend(runner)
    backend.start()

    frame = backend.preview_frame()

    assert frame == FRAME_ONE
    assert runner.start_args == [build_preview_command(VID_PATH, RpicamSettings())]


def test_rpicam_vid_exiting_before_first_frame_is_unavailable_and_released() -> None:
    runner = FakeRunner()
    runner.next_process = lambda: FakeProcess(exit_code=1)
    backend = make_backend(runner)
    backend.start()

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()

    assert runner.processes[0].closed


def test_missing_first_frame_times_out_and_terminates_preview() -> None:
    runner = FakeRunner()
    runner.next_process = FakeProcess
    backend = make_backend(runner)
    backend.start()

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()

    assert runner.processes[0].interrupts == 1
    assert runner.processes[0].closed


def test_preview_exit_after_frames_is_operation_error_and_stops_backend() -> None:
    runner = FakeRunner()
    runner.next_process = lambda: FakeProcess([FRAME_ONE])
    backend = make_backend(runner)
    backend.start()
    assert backend.preview_frame() == FRAME_ONE

    runner.processes[0].end(1)

    with pytest.raises(CameraOperationError):
        backend.preview_frame()
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_stop_terminates_preview_with_sigint_and_closes_it() -> None:
    runner = FakeRunner()
    runner.next_process = lambda: FakeProcess([FRAME_ONE])
    backend = make_backend(runner)
    backend.start()
    backend.preview_frame()

    backend.stop()

    assert runner.processes[0].interrupts == 1
    assert runner.processes[0].kills == 0
    assert runner.processes[0].closed


def test_stubborn_preview_keeps_ownership_and_stop_can_be_retried() -> None:
    runner = FakeRunner()
    stubborn = FakeProcess([FRAME_ONE], ignore_interrupt=True, ignore_kill=True)
    runner.next_process = lambda: stubborn
    backend = make_backend(runner)
    backend.start()
    backend.preview_frame()

    with pytest.raises(CameraOperationError):
        backend.stop()
    assert not stubborn.closed

    stubborn.ignore_kill = False
    stubborn.ignore_interrupt = False
    backend.stop()

    assert stubborn.closed
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_capture_stops_preview_before_running_still_and_publishes_jpeg(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    preview = FakeProcess([FRAME_ONE])
    runner.next_process = lambda: preview
    observed_closed: list[bool] = []

    def handler(args: tuple[str, ...], timeout: float) -> FiniteCommandResult:
        """Record whether preview was released, then write the still."""
        observed_closed.append(preview.closed)
        return write_jpeg_still()(args, timeout)

    runner.run_handler = handler
    backend = make_backend(runner)
    backend.start()
    backend.preview_frame()
    destination = tmp_path / "photo.jpg"

    backend.capture(destination)

    assert observed_closed == [True]
    assert runner.run_args[0][:-1] == build_still_command(
        STILL_PATH, RpicamSettings(), Path("unused")
    )[:-1]
    assert runner.run_args[0][-1] != str(destination)
    assert destination.read_bytes() == make_jpeg()
    assert sorted(item.name for item in tmp_path.iterdir()) == ["photo.jpg"]
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_capture_without_start_is_unavailable(tmp_path: Path) -> None:
    backend = make_backend(FakeRunner())

    with pytest.raises(CameraUnavailableError):
        backend.capture(tmp_path / "photo.jpg")


def test_capture_nonzero_exit_leaves_no_output_or_temporary_file(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.run_handler = write_jpeg_still(returncode=1)
    backend = make_backend(runner)
    backend.start()
    destination = tmp_path / "photo.jpg"

    with pytest.raises(CameraOperationError):
        backend.capture(destination)

    assert list(tmp_path.iterdir()) == []


def test_capture_invalid_jpeg_is_rejected_and_not_published(tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.run_handler = write_jpeg_still(payload=b"not a jpeg")
    backend = make_backend(runner)
    backend.start()
    destination = tmp_path / "photo.jpg"

    with pytest.raises(CameraOperationError):
        backend.capture(destination)

    assert list(tmp_path.iterdir()) == []


def test_capture_timeout_is_operation_error_and_leaves_no_file(tmp_path: Path) -> None:
    runner = FakeRunner()

    def timeout_handler(args: tuple[str, ...], timeout: float) -> FiniteCommandResult:
        """Simulate rpicam-still exceeding its finite-command timeout."""
        raise ProcessTimeoutError("timed out")

    runner.run_handler = timeout_handler
    backend = make_backend(runner)
    backend.start()

    with pytest.raises(CameraOperationError):
        backend.capture(tmp_path / "photo.jpg")

    assert list(tmp_path.iterdir()) == []


def test_missing_still_executable_fails_start(tmp_path: Path) -> None:
    backend = make_backend(FakeRunner(still=None))

    with pytest.raises(CameraUnavailableError):
        backend.start()


def test_default_settings_build_documented_commands() -> None:
    preview = build_preview_command(VID_PATH, RpicamSettings())
    still = build_still_command(STILL_PATH, RpicamSettings(), Path("/tmp/out.jpg"))

    assert preview == (
        VID_PATH,
        "--nopreview",
        "-t",
        "0",
        "--codec",
        "mjpeg",
        "--width",
        "1280",
        "--height",
        "720",
        "--awb",
        "auto",
        "--flush",
        "-o",
        "-",
    )
    assert still == (
        STILL_PATH,
        "--nopreview",
        "--immediate",
        "-t",
        "1",
        "--encoding",
        "jpg",
        "--quality",
        "93",
        "--awb",
        "auto",
        "-o",
        "/tmp/out.jpg",
    )


def test_applied_jpeg_quality_reaches_next_still_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    backend = make_backend(runner)
    backend.start()
    capability = next(
        item for item in backend.get_capabilities() if item.identifier == "jpeg_quality"
    )
    backend.apply_setting(validate_camera_setting(capability, 72))

    backend.capture(tmp_path / "photo.jpg")

    assert "--quality" in runner.run_args[0]
    assert runner.run_args[0][runner.run_args[0].index("--quality") + 1] == "72"


def test_restart_required_preview_size_cannot_be_applied_at_runtime() -> None:
    backend = make_backend(FakeRunner())
    capability = next(
        item for item in backend.get_capabilities() if item.identifier == "preview_size"
    )

    with pytest.raises(ValueError):
        backend.apply_setting(validate_camera_setting(capability, "1920x1080"))


def test_invalid_persisted_settings_are_rejected() -> None:
    backend = make_backend(FakeRunner())

    with pytest.raises(ValueError):
        backend.configure_settings({"white_balance": "rainbow"})
    with pytest.raises(ValueError):
        backend.configure_settings({"jpeg_quality": 10})


def test_unknown_persisted_settings_are_ignored() -> None:
    backend = make_backend(FakeRunner())

    backend.configure_settings({"shell_command": "rm -rf /"})

    assert all(item.identifier != "shell_command" for item in backend.get_capabilities())
