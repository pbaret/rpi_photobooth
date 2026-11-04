"""Verify rpicam still-capture settings, validation rules and argument mapping.

These tests exercise the pure settings and command-construction layers; no
process is launched and no rpicam executable is required.
"""

from pathlib import Path

import pytest

from photobooth.camera.rpicam import build_still_command
from photobooth.camera.rpicam_settings import (
    AutofocusMode,
    ExposureControl,
    HdrMode,
    NormalizedRectangle,
    RpicamSettings,
    capabilities_for,
    settings_from_mapping,
)
from photobooth.camera.settings import ValidatedCameraSetting

STILL = "/usr/bin/rpicam-still"
OUTPUT = Path("/tmp/out.jpg")


def command(**requested: bool | int | float | str) -> tuple[str, ...]:
    """Build the still command after applying persisted-style requests to defaults."""
    return build_still_command(STILL, settings_from_mapping(RpicamSettings(), requested), OUTPUT)


def option(args: tuple[str, ...], name: str) -> str:
    """Return the token following ``name`` in ``args``."""
    return args[args.index(name) + 1]


def test_default_low_light_profile_values() -> None:
    settings = RpicamSettings()

    assert (settings.still_width, settings.still_height) == (4608, 2592)
    assert settings.jpeg_quality == 95
    assert settings.exposure_control is ExposureControl.AUTO
    assert settings.metering.value == "centre"
    assert settings.exposure_mode.value == "normal"
    assert settings.ev == 0.3
    assert settings.white_balance.value == "auto"
    assert (settings.brightness, settings.contrast, settings.saturation) == (0.0, 1.0, 1.0)
    assert settings.sharpness == 1.1
    assert settings.denoise.value == "cdn_hq"
    assert settings.autofocus_mode is AutofocusMode.AUTO
    assert settings.autofocus_range.value == "normal"
    assert settings.autofocus_speed.value == "fast"
    assert settings.autofocus_window == NormalizedRectangle(0.2, 0.15, 0.6, 0.7)
    assert settings.autofocus_on_capture is True
    assert settings.hdr is HdrMode.OFF
    assert settings.verbosity == 2


def test_default_command_omits_shutter_gain_and_lens_and_scans_on_capture() -> None:
    args = command()

    assert "--shutter" not in args
    assert "--gain" not in args
    assert "--analoggain" not in args
    assert "--lens-position" not in args
    assert "--autofocus-on-capture" in args
    assert "--immediate" not in args
    assert "--hdr=off" in args
    assert "--verbose=2" in args
    assert args[-2:] == ("-o", str(OUTPUT))


@pytest.mark.parametrize(
    ("requested", "flag", "expected"),
    [
        ({"still_width": 2304}, "--width", "2304"),
        ({"still_height": 1296}, "--height", "1296"),
        ({"jpeg_quality": 88}, "--quality", "88"),
        ({"metering": "spot"}, "--metering", "spot"),
        ({"exposure_mode": "sport"}, "--exposure", "sport"),
        ({"ev": -0.5}, "--ev", "-0.5"),
        ({"white_balance": "tungsten"}, "--awb", "tungsten"),
        ({"brightness": -0.2}, "--brightness", "-0.2"),
        ({"contrast": 1.25}, "--contrast", "1.25"),
        ({"saturation": 0.0}, "--saturation", "0"),
        ({"sharpness": 1.5}, "--sharpness", "1.5"),
        ({"denoise": "cdn_fast"}, "--denoise", "cdn_fast"),
        ({"autofocus_mode": "continuous"}, "--autofocus-mode", "continuous"),
        ({"autofocus_range": "macro"}, "--autofocus-range", "macro"),
        ({"autofocus_speed": "normal"}, "--autofocus-speed", "normal"),
        (
            {"autofocus_window_x": 0.25, "autofocus_window_width": 0.5},
            "--autofocus-window",
            "0.25,0.15,0.5,0.7",
        ),
    ],
)
def test_each_setting_maps_to_its_allowlisted_argument(
    requested: dict[str, bool | int | float | str], flag: str, expected: str
) -> None:
    assert option(command(**requested), flag) == expected


@pytest.mark.parametrize("mode", ["auto", "sensor", "single-exp", "off"])
def test_hdr_uses_attached_value_form(mode: str) -> None:
    assert f"--hdr={mode}" in command(hdr=mode)


def test_verbosity_uses_attached_value_form() -> None:
    args = command(verbosity=0)

    assert "--verbose=0" in args
    assert "--verbose" not in args


def test_manual_exposure_emits_shutter_and_canonical_gain() -> None:
    args = command(exposure_control="manual", shutter_us=33333, gain=2.5)

    assert option(args, "--shutter") == "33333"
    assert option(args, "--gain") == "2.5"
    assert "--analoggain" not in args


def test_automatic_exposure_ignores_stored_manual_values() -> None:
    args = command(exposure_control="auto", shutter_us=33333, gain=2.5)

    assert "--shutter" not in args
    assert "--gain" not in args


def test_manual_focus_emits_lens_position_and_no_autofocus_arguments() -> None:
    args = command(autofocus_mode="manual", lens_position=0.7, autofocus_on_capture=True)

    assert option(args, "--lens-position") == "0.7"
    assert "--autofocus-on-capture" not in args
    assert "--autofocus-window" not in args
    assert "--autofocus-range" not in args
    assert "--autofocus-speed" not in args
    assert "--immediate" in args


@pytest.mark.parametrize("mode", ["auto", "continuous"])
def test_lens_position_is_never_emitted_outside_manual_focus(mode: str) -> None:
    assert "--lens-position" not in command(autofocus_mode=mode, lens_position=0.7)


def test_disabling_autofocus_on_capture_restores_immediate_capture() -> None:
    args = command(autofocus_on_capture=False)

    assert "--autofocus-on-capture" not in args
    assert "--immediate" in args


@pytest.mark.parametrize(
    ("requested", "identifier"),
    [
        ({"still_width": 0}, "still_width"),
        ({"still_width": 5000}, "still_width"),
        ({"still_height": -2}, "still_height"),
        ({"jpeg_quality": 10}, "jpeg_quality"),
        ({"jpeg_quality": 101}, "jpeg_quality"),
        ({"brightness": 1.5}, "brightness"),
        ({"gain": 0.0}, "gain"),
        ({"gain": 32.0}, "gain"),
        ({"shutter_us": 0}, "shutter_us"),
        ({"shutter_us": -16667}, "shutter_us"),
        ({"contrast": 0.0}, "contrast"),
        ({"sharpness": 0.0}, "sharpness"),
        ({"ev": 5.0}, "ev"),
        ({"metering": "matrix"}, "metering"),
        ({"autofocus_mode": "default"}, "autofocus_mode"),
        ({"hdr": "on"}, "hdr"),
        ({"denoise": "cdn_hq --shutter 1"}, "denoise"),
        ({"white_balance": "auto; rm -rf /"}, "white_balance"),
        ({"verbosity": 3}, "verbosity"),
        ({"autofocus_window_width": 0.0}, "autofocus_window_width"),
        ({"autofocus_window_x": -0.1}, "autofocus_window_x"),
        ({"autofocus_window_x": 0.5}, "autofocus_window_width"),
        ({"autofocus_window_y": 0.4}, "autofocus_window_height"),
        ({"lens_position": -1.0}, "lens_position"),
        ({"gain": "4.0"}, "gain"),
        ({"autofocus_on_capture": "true"}, "autofocus_on_capture"),
    ],
)
def test_invalid_values_are_rejected_with_identifier(
    requested: dict[str, bool | int | float | str], identifier: str
) -> None:
    with pytest.raises(ValueError) as caught:
        settings_from_mapping(RpicamSettings(), requested)

    assert str(caught.value).startswith(identifier)


def test_read_only_diagnostic_cannot_be_configured() -> None:
    with pytest.raises(ValueError):
        settings_from_mapping(RpicamSettings(), {"last_still_command": "--shell"})


def test_rectangle_may_touch_frame_edges() -> None:
    rectangle = NormalizedRectangle(0.3, 0.0, 0.7, 1.0)

    assert rectangle.to_argument() == "0.3,0,0.7,1"


@pytest.mark.parametrize(
    "values",
    [(0.0, 0.0, 0.0, 0.5), (0.0, 0.0, 0.5, 1.2), (1.1, 0.0, 0.1, 0.1), (0.6, 0.6, 0.5, 0.5)],
)
def test_rectangle_outside_normalized_frame_is_rejected(
    values: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError):
        NormalizedRectangle(*values)


def test_multi_field_window_update_validates_final_state() -> None:
    """Moving the window right and narrowing it is valid once both values apply."""
    settings = settings_from_mapping(
        RpicamSettings(), {"autofocus_window_x": 0.5, "autofocus_window_width": 0.4}
    )

    assert settings.autofocus_window == NormalizedRectangle(0.5, 0.15, 0.4, 0.7)


def test_inconsistent_stored_window_refuses_command_construction() -> None:
    """A transient invalid window must never reach rpicam."""
    settings = settings_from_mapping(
        RpicamSettings(), {"autofocus_window_x": 0.5, "autofocus_window_width": 0.4}
    )
    shifted = settings.with_setting(ValidatedCameraSetting("autofocus_window_width", 0.6))

    with pytest.raises(ValueError):
        build_still_command(STILL, shifted, OUTPUT)


def test_capabilities_carry_groups_units_and_dependencies() -> None:
    capabilities = {item.identifier: item for item in capabilities_for(RpicamSettings(), None)}

    assert capabilities["shutter_us"].unit == "µs"
    assert capabilities["shutter_us"].group == "Exposure"
    assert capabilities["shutter_us"].active_when is not None
    assert capabilities["shutter_us"].active_when.values == ("manual",)
    assert capabilities["lens_position"].active_when is not None
    assert capabilities["lens_position"].active_when.values == ("manual",)
    assert capabilities["autofocus_on_capture"].active_when is not None
    assert "manual" not in capabilities["autofocus_on_capture"].active_when.values
    assert capabilities["jpeg_quality"].capture_only
    assert not capabilities["white_balance"].capture_only
    assert capabilities["preview_size"].restart_required
    assert capabilities["last_still_command"].read_only
    assert capabilities["last_still_command"].effective_value is None
    assert "analoggain" not in capabilities
    assert capabilities["hdr"].allowed_values == ("off", "auto", "sensor", "single-exp")
