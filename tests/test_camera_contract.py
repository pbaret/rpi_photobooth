"""Verify that a small hardware-free implementation can use CameraBackend."""

from pathlib import Path

import pytest

from photobooth.camera import (
    CameraBackend,
    CameraOperationError,
    CameraUnavailableError,
)


class FakeCameraBackend:
    """Provide deterministic frames and capture output for contract tests."""

    def __init__(self) -> None:
        """Initialize the fake with no active camera resources."""
        self._started = False

    def start(self) -> None:
        """Make preview available; repeated starts retain the same state."""
        self._started = True

    def stop(self) -> None:
        """Stop preview; repeated stops are harmless."""
        self._started = False

    def preview_frame(self) -> bytes:
        """Return a deterministic frame or report that preview is stopped."""
        if not self._started:
            raise CameraUnavailableError("camera is not started")
        return b"jpeg-preview"

    def capture(self, output_path: Path) -> None:
        """Write a deterministic still and release the fake camera."""
        if not self._started:
            raise CameraUnavailableError("camera is not started")
        try:
            output_path.write_bytes(b"jpeg-still")
        except OSError as error:
            self._started = False
            raise CameraOperationError("capture output could not be written") from error
        self._started = False


def test_fake_backend_satisfies_contract_and_capture_stops_preview(
    tmp_path: Path,
) -> None:
    """Exercise the typed contract without a webcam or camera dependencies."""
    backend: CameraBackend = FakeCameraBackend()

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()

    backend.start()
    assert backend.preview_frame() == b"jpeg-preview"

    output_path = tmp_path / "capture.jpg"
    backend.capture(output_path)

    assert output_path.read_bytes() == b"jpeg-still"
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()

    backend.stop()
    backend.stop()