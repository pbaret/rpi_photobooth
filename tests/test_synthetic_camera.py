"""Verify the synthetic camera's JPEG output and lifecycle without hardware."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from photobooth.camera import (
    CameraBackend,
    CameraOperationError,
    CameraSettingType,
    CameraUnavailableError,
    SyntheticCameraBackend,
    ValidatedCameraSetting,
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


def test_synthetic_capabilities_cover_test_control_shapes() -> None:
    """Synthetic-only declarations cover editable, enumerated, readonly, and restart controls."""
    backend = SyntheticCameraBackend()
    capabilities = {item.identifier: item for item in backend.get_capabilities()}

    assert capabilities["synthetic_overlay"].value_type is CameraSettingType.BOOLEAN
    assert capabilities["synthetic_quality"].minimum == 30
    assert capabilities["synthetic_quality"].maximum == 95
    assert capabilities["synthetic_scene"].allowed_values == ("classic", "colorful")
    assert capabilities["synthetic_scene"].restart_required
    assert capabilities["synthetic_running"].read_only


def test_synthetic_live_setting_is_effective_but_restart_setting_is_not_applied() -> None:
    """Live requests update effective state while restart-required requests are rejected for immediate apply."""
    backend = SyntheticCameraBackend()

    effective_value = backend.apply_setting(
        ValidatedCameraSetting("synthetic_overlay", False)
    )
    assert effective_value is False
    capabilities = {item.identifier: item for item in backend.get_capabilities()}
    assert capabilities["synthetic_overlay"].requested_value is False
    assert capabilities["synthetic_overlay"].effective_value is False

    with pytest.raises(ValueError, match="without restart"):
        backend.apply_setting(ValidatedCameraSetting("synthetic_scene", "colorful"))
    with pytest.raises(ValueError, match="read-only"):
        backend.apply_setting(ValidatedCameraSetting("synthetic_running", True))


def test_saved_supported_synthetic_request_is_configured_at_startup() -> None:
    """A new backend loads its declared persisted value while ignoring unknown keys."""
    backend = SyntheticCameraBackend()
    backend.configure_settings(
        {"synthetic_scene": "colorful", "future_camera_setting": 42}
    )

    capabilities = {item.identifier: item for item in backend.get_capabilities()}
    assert capabilities["synthetic_scene"].requested_value == "colorful"
    assert capabilities["synthetic_scene"].effective_value == "classic"
    backend.start()
    capabilities = {item.identifier: item for item in backend.get_capabilities()}
    assert capabilities["synthetic_scene"].effective_value == "colorful"