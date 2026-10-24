"""Verify the synthetic camera's JPEG output and lifecycle without hardware."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from photobooth.camera import (
    CameraBackend,
    CameraOperationError,
    CameraUnavailableError,
    SyntheticCameraBackend,
)


def assert_valid_jpeg(image_bytes: bytes) -> None:
    """Confirm bytes contain a decodable JPEG with the synthetic frame size."""
    with Image.open(BytesIO(image_bytes)) as image:
        assert image.format == "JPEG"
        assert image.size == (640, 480)
        image.verify()


def test_start_is_idempotent_and_preview_returns_deterministic_jpeg() -> None:
    """Repeated starts retain preview and every frame depicts fixed content."""
    backend: CameraBackend = SyntheticCameraBackend()

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()

    backend.start()
    backend.start()
    first_frame = backend.preview_frame()
    second_frame = backend.preview_frame()

    assert_valid_jpeg(first_frame)
    assert_valid_jpeg(second_frame)
    with Image.open(BytesIO(first_frame)) as first_image:
        first_pixels = first_image.convert("RGB").tobytes()
    with Image.open(BytesIO(second_frame)) as second_image:
        assert first_pixels == second_image.convert("RGB").tobytes()


def test_capture_writes_jpeg_and_stops_preview(tmp_path: Path) -> None:
    """A still is valid JPEG data and successful capture releases preview."""
    backend = SyntheticCameraBackend()
    output_path = tmp_path / "capture.jpg"

    backend.start()
    backend.capture(output_path)

    assert_valid_jpeg(output_path.read_bytes())
    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()
    backend.stop()
    backend.stop()


def test_stop_is_idempotent_and_disables_preview() -> None:
    """Stopping active preview releases it and repeated stop remains valid."""
    backend = SyntheticCameraBackend()
    backend.start()

    backend.stop()
    backend.stop()

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()


def test_capture_failure_stops_preview(tmp_path: Path) -> None:
    """A failed write is translated and still releases the active backend."""
    backend = SyntheticCameraBackend()

    backend.start()
    with pytest.raises(CameraOperationError):
        backend.capture(tmp_path / "missing" / "capture.jpg")

    with pytest.raises(CameraUnavailableError):
        backend.preview_frame()