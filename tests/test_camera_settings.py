"""Verify backend capability declarations and typed setting validation."""

import pytest

from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingType,
    validate_camera_setting,
)


def test_capability_types_validate_boolean_integer_float_and_enum() -> None:
    """Each declared type accepts values of its own shape only."""
    boolean = CameraSettingCapability(
        "enabled", "Enabled", CameraSettingType.BOOLEAN, False
    )
    integer = CameraSettingCapability(
        "width", "Width", CameraSettingType.INTEGER, 640, minimum=320, maximum=1920, step=160
    )
    floating = CameraSettingCapability(
        "gain", "Gain", CameraSettingType.FLOAT, 1.0, minimum=0.0, maximum=4.0, step=0.5
    )
    mode = CameraSettingCapability(
        "mode", "Mode", CameraSettingType.ENUM, "auto", allowed_values=("auto", "manual")
    )

    assert validate_camera_setting(boolean, True).value is True
    assert validate_camera_setting(integer, 800).value == 800
    assert validate_camera_setting(floating, 1.5).value == 1.5
    assert validate_camera_setting(mode, "manual").value == "manual"
    with pytest.raises(ValueError, match="invalid value type"):
        validate_camera_setting(integer, True)


@pytest.mark.parametrize("value", [319, 2000, 801])
def test_bounded_integer_rejects_out_of_range_or_step_values(value: int) -> None:
    """Integer bounds and increments are enforced independently of HTML input."""
    capability = CameraSettingCapability(
        "width", "Width", CameraSettingType.INTEGER, 640, minimum=320, maximum=1920, step=160
    )

    with pytest.raises(ValueError):
        validate_camera_setting(capability, value)


def test_enum_rejects_undeclared_values_and_read_only_is_explicit() -> None:
    """Enums accept only declared choices and capability metadata retains readonly state."""
    capability = CameraSettingCapability(
        "mode",
        "Mode",
        CameraSettingType.ENUM,
        "auto",
        allowed_values=("auto", "manual"),
        read_only=True,
        restart_required=True,
    )

    with pytest.raises(ValueError, match="declared values"):
        validate_camera_setting(capability, "continuous")
    assert capability.read_only
    assert capability.restart_required