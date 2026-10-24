"""Verify OpenCV camera behavior with a fake device and no webcam hardware."""

from pathlib import Path
from typing import Callable

import pytest

import photobooth.camera.opencv as opencv_camera
from photobooth.camera import (
    CameraOperationError,
    CameraUnavailableError,
    OpenCVCameraBackend,
)


class FakeEncodedImage:
    """Provide the byte conversion exposed by OpenCV's encoded image buffer."""

    def __init__(self, content: bytes) -> None:
        """Retain the encoded bytes returned to the backend."""
        self.content = content

    def tobytes(self) -> bytes:
        """Return the encoded image payload."""
        return self.content


class FakeCapture:
    """Record camera operations and return deterministic negotiated dimensions."""

    def __init__(self, opened: bool = True, read_succeeds: bool = True) -> None:
        """Configure whether acquisition and subsequent frame reads succeed."""
        self.opened = opened
        self.read_succeeds = read_succeeds
        self.release_count = 0
        self.requested_properties: list[tuple[int, float]] = []
        self.frame = object()

    def isOpened(self) -> bool:
        """Return the configured acquisition result."""
        return self.opened

    def set(self, property_id: int, value: float) -> bool:
        """Record a requested property without assuming the driver accepts it."""
        self.requested_properties.append((property_id, value))
        return True

    def get(self, property_id: int) -> float:
        """Return the fake device's effective 1280-by-720 dimensions."""
        if property_id == opencv_camera.cv2.CAP_PROP_FRAME_WIDTH:
            return 1280.0
        if property_id == opencv_camera.cv2.CAP_PROP_FRAME_HEIGHT:
            return 720.0
        return 0.0

    def read(self) -> tuple[bool, object]:
        """Return a fixed opaque frame or the configured read failure."""
        return self.read_succeeds, self.frame

    def release(self) -> None:
        """Count release requests from the backend."""
        self.release_count += 1


def install_fake_opencv(
    monkeypatch: pytest.MonkeyPatch,
    capture_factory: Callable[[int], FakeCapture],
) -> list[object]:
    """Replace the camera and image-encoding boundaries with deterministic fakes."""
    captured_frames: list[object] = []

    def flip_frame(frame: object, _direction: int) -> object:
        """Record the preview image passed to OpenCV's mirror operation."""
        captured_frames.append(frame)
        return frame

    def encode_frame(_extension: str, _frame: object) -> tuple[bool, FakeEncodedImage]:
        """Return deterministic JPEG bytes for either preview or capture."""
        return True, FakeEncodedImage(b"jpeg-bytes")

    monkeypatch.setattr(opencv_camera.cv2, "VideoCapture", capture_factory)
    monkeypatch.setattr(opencv_camera.cv2, "flip", flip_frame)
    monkeypatch.setattr(opencv_camera.cv2, "imencode", encode_frame)
    return captured_frames


def test_start_is_lazy_idempotent_and_reports_effective_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One device handle is opened and requested dimensions may be negotiated."""
    captures: list[FakeCapture] = []

    def create_capture(camera_index: int) -> FakeCapture:
        """Record device index and make one fake capture handle."""
        assert camera_index == 2
        capture = FakeCapture()
        captures.append(capture)
        return capture

    install_fake_opencv(monkeypatch, create_capture)
    backend = OpenCVCameraBackend(camera_index=2, requested_width=640, requested_height=480)

    assert backend.requested_resolution == (640, 480)
    assert backend.effective_resolution is None
    backend.start()
    backend.start()

    assert len(captures) == 1
    assert captures[0].requested_properties == [
        (opencv_camera.cv2.CAP_PROP_FRAME_WIDTH, 640.0),
        (opencv_camera.cv2.CAP_PROP_FRAME_HEIGHT, 480.0),
    ]
    assert backend.effective_resolution == (1280, 720)
    backend.stop()
    backend.stop()
    assert captures[0].release_count == 1
    assert backend.effective_resolution is None


def test_preview_is_mirrored_and_jpeg_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preview frames are mirrored while the device remains owned."""
    fake_capture = FakeCapture()
    mirrored_frames = install_fake_opencv(monkeypatch, lambda _index: fake_capture)
    backend = OpenCVCameraBackend()

    backend.start()
    frame = backend.preview_frame()

    assert frame == b"jpeg-bytes"
    assert mirrored_frames == [fake_capture.frame]
    assert fake_capture.release_count == 0
    backend.stop()


def test_capture_keeps_camera_orientation_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Capture writes JPEG bytes without preview mirroring and releases the handle."""
    fake_capture = FakeCapture()
    mirrored_frames = install_fake_opencv(monkeypatch, lambda _index: fake_capture)
    backend = OpenCVCameraBackend()
    output_path = tmp_path / "capture.jpg"

    backend.start()
    backend.capture(output_path)

    assert output_path.read_bytes() == b"jpeg-bytes"
    assert mirrored_frames == []
    assert fake_capture.release_count == 1
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_unavailable_device_is_released_and_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy or unavailable device is reported without leaking its handle."""
    fake_capture = FakeCapture(opened=False)
    install_fake_opencv(monkeypatch, lambda _index: fake_capture)
    backend = OpenCVCameraBackend()

    with pytest.raises(CameraUnavailableError, match="unavailable or busy"):
        backend.start()

    assert fake_capture.release_count == 1
    assert backend.effective_resolution is None


def test_failed_preview_read_releases_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read failure becomes a camera operation error and stops preview."""
    fake_capture = FakeCapture(read_succeeds=False)
    install_fake_opencv(monkeypatch, lambda _index: fake_capture)
    backend = OpenCVCameraBackend()
    backend.start()

    with pytest.raises(CameraOperationError, match="preview frame"):
        backend.preview_frame()

    assert fake_capture.release_count == 1
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_failed_capture_write_releases_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A caller-path write failure is translated and still releases the camera."""
    fake_capture = FakeCapture()
    install_fake_opencv(monkeypatch, lambda _index: fake_capture)
    backend = OpenCVCameraBackend()
    backend.start()

    with pytest.raises(CameraOperationError, match="capture failed"):
        backend.capture(tmp_path / "missing" / "capture.jpg")

    assert fake_capture.release_count == 1