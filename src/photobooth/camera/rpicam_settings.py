"""Model, validate and declare the allowlisted rpicam camera settings.

This module is the settings-validation layer of the rpicam backend. It owns
the typed :class:`RpicamSettings` value, the per-setting capability
declarations shown in administration, and the rules that span several
settings (such as the autofocus window staying inside the frame). Command
construction lives in :mod:`photobooth.camera.rpicam` and only consumes
validated settings; nothing here launches processes.

Every capability identifier is also the name of the matching
:class:`RpicamSettings` field, so persisted ``camera_settings`` keys map to
fields without an intermediate translation table. Only values listed here can
reach a command line, and enum values were confirmed against
``rpicam-still --help`` from rpicam-apps v1.14.0.

Bounds are application bounds, deliberately narrower than what the rpicam
parser accepts, chosen for a Camera Module 3 photobooth: subjects 1-2 m away
in relatively low light. The defaults form a provisional low-light portrait
profile that still requires on-site tuning.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Final

from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingCondition,
    CameraSettingType,
    CameraSettingValue,
    ValidatedCameraSetting,
    validate_camera_setting,
)

PREVIEW_SIZES: Final[dict[str, tuple[int, int]]] = {
    "640x480": (640, 480),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}
JPEG_QUALITY_MINIMUM: Final = 50
JPEG_QUALITY_MAXIMUM: Final = 100
# Camera Module 3 full sensor resolution; larger requests would be upscaled.
STILL_WIDTH_MAXIMUM: Final = 4608
STILL_HEIGHT_MAXIMUM: Final = 2592
_RECTANGLE_TOLERANCE: Final = 1e-9


class WhiteBalanceMode(str, Enum):
    """AWB presets accepted by rpicam ``--awb``; ``custom`` needs a tuning file and is excluded."""

    AUTO = "auto"
    INCANDESCENT = "incandescent"
    TUNGSTEN = "tungsten"
    FLUORESCENT = "fluorescent"
    INDOOR = "indoor"
    DAYLIGHT = "daylight"
    CLOUDY = "cloudy"


class DenoiseMode(str, Enum):
    """Denoise modes accepted by rpicam ``--denoise``."""

    AUTO = "auto"
    OFF = "off"
    CDN_OFF = "cdn_off"
    CDN_FAST = "cdn_fast"
    CDN_HQ = "cdn_hq"


class HdrMode(str, Enum):
    """HDR values accepted by rpicam ``--hdr``.

    The parser accepting a value does not prove the camera honours it; see
    the configuration documentation for what was observed on Camera Module 3.
    """

    OFF = "off"
    AUTO = "auto"
    SENSOR = "sensor"
    SINGLE_EXP = "single-exp"


class ExposureControl(str, Enum):
    """Select automatic exposure or a fixed shutter duration and gain."""

    AUTO = "auto"
    MANUAL = "manual"


class MeteringMode(str, Enum):
    """Metering modes for ``--metering``; ``custom`` needs a tuning file and is excluded."""

    CENTRE = "centre"
    SPOT = "spot"
    AVERAGE = "average"


class ExposureMode(str, Enum):
    """Automatic-exposure profiles accepted by rpicam ``--exposure``."""

    NORMAL = "normal"
    SPORT = "sport"


class AutofocusMode(str, Enum):
    """Autofocus algorithm modes accepted by rpicam ``--autofocus-mode``."""

    AUTO = "auto"
    CONTINUOUS = "continuous"
    MANUAL = "manual"


class AutofocusRange(str, Enum):
    """Focus-distance ranges scanned by autofocus (``--autofocus-range``)."""

    NORMAL = "normal"
    MACRO = "macro"
    FULL = "full"


class AutofocusSpeed(str, Enum):
    """Lens movement speed during autofocus (``--autofocus-speed``)."""

    NORMAL = "normal"
    FAST = "fast"


@dataclass(frozen=True)
class NormalizedRectangle:
    """A rectangle in frame-relative coordinates, origin at the top-left corner.

    All values are fractions of the full image: ``x`` and ``y`` locate the
    top-left corner, ``width`` and ``height`` extend right and down. The
    rectangle must lie entirely inside the frame. Validation errors start
    with the offending component name (``x``, ``y``, ``width``, ``height``).
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        """Reject non-finite, empty, or out-of-frame rectangles with ``ValueError``."""
        for name in ("x", "y", "width", "height"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be a finite number")
        if not 0.0 <= self.x <= 1.0:
            raise ValueError("x must be between 0.0 and 1.0")
        if not 0.0 <= self.y <= 1.0:
            raise ValueError("y must be between 0.0 and 1.0")
        if not 0.0 < self.width <= 1.0:
            raise ValueError("width must be greater than 0.0 and at most 1.0")
        if not 0.0 < self.height <= 1.0:
            raise ValueError("height must be greater than 0.0 and at most 1.0")
        if self.x + self.width > 1.0 + _RECTANGLE_TOLERANCE:
            raise ValueError("width extends beyond the right edge (x + width > 1.0)")
        if self.y + self.height > 1.0 + _RECTANGLE_TOLERANCE:
            raise ValueError("height extends beyond the bottom edge (y + height > 1.0)")

    def to_argument(self) -> str:
        """Return the ``x,y,width,height`` form expected by ``--autofocus-window``."""
        return ",".join(format_number(value) for value in (self.x, self.y, self.width, self.height))


def format_number(value: float) -> str:
    """Render a validated number compactly for a command line (``1.0`` -> ``1``).

    Application bounds and steps keep values far from the range where ``g``
    formatting would switch to exponent notation.
    """
    return format(value, "g")


_ENUM_FIELDS: Final[dict[str, type[Enum]]] = {
    "white_balance": WhiteBalanceMode,
    "denoise": DenoiseMode,
    "hdr": HdrMode,
    "exposure_control": ExposureControl,
    "metering": MeteringMode,
    "exposure_mode": ExposureMode,
    "autofocus_mode": AutofocusMode,
    "autofocus_range": AutofocusRange,
    "autofocus_speed": AutofocusSpeed,
}
_INTEGER_FIELDS: Final = frozenset(
    {"jpeg_quality", "still_width", "still_height", "shutter_us", "verbosity"}
)
_BOOLEAN_FIELDS: Final = frozenset({"autofocus_on_capture"})

LAST_STILL_COMMAND: Final = "last_still_command"

_GROUP_PREVIEW: Final = "Preview"
_GROUP_IMAGE: Final = "Image"
_GROUP_EXPOSURE: Final = "Exposure"
_GROUP_RENDERING: Final = "White balance and rendering"
_GROUP_AUTOFOCUS: Final = "Autofocus"
_GROUP_DIAGNOSTICS: Final = "Diagnostics"

_MANUAL_EXPOSURE: Final = CameraSettingCondition("exposure_control", (ExposureControl.MANUAL.value,))
_AUTOMATIC_FOCUS: Final = CameraSettingCondition(
    "autofocus_mode", (AutofocusMode.AUTO.value, AutofocusMode.CONTINUOUS.value)
)
_MANUAL_FOCUS: Final = CameraSettingCondition("autofocus_mode", (AutofocusMode.MANUAL.value,))


def _choices(enum_type: type[Enum]) -> tuple[CameraSettingValue, ...]:
    """Return the persisted string values of an enum in declaration order."""
    return tuple(str(member.value) for member in enum_type)


def _float_setting(
    identifier: str,
    label: str,
    default: float,
    minimum: float,
    maximum: float,
    step: float,
    group: str,
    description: str,
    *,
    unit: str = "",
    active_when: CameraSettingCondition | None = None,
) -> CameraSettingCapability:
    """Declare one bounded still-capture float control."""
    return CameraSettingCapability(
        identifier=identifier,
        label=label,
        value_type=CameraSettingType.FLOAT,
        default_value=default,
        minimum=minimum,
        maximum=maximum,
        step=step,
        description=description,
        group=group,
        unit=unit,
        capture_only=True,
        active_when=active_when,
    )


def _enum_setting(
    identifier: str,
    label: str,
    default: Enum,
    group: str,
    description: str,
    *,
    capture_only: bool = True,
    active_when: CameraSettingCondition | None = None,
) -> CameraSettingCapability:
    """Declare one enum control whose allowed values come from its enum type."""
    return CameraSettingCapability(
        identifier=identifier,
        label=label,
        value_type=CameraSettingType.ENUM,
        default_value=str(default.value),
        allowed_values=_choices(type(default)),
        description=description,
        group=group,
        capture_only=capture_only,
        active_when=active_when,
    )


# Order defines the admin presentation order; groups must stay contiguous.
BASE_CAPABILITIES: Final[tuple[CameraSettingCapability, ...]] = (
    CameraSettingCapability(
        identifier="preview_size",
        label="Preview size",
        value_type=CameraSettingType.ENUM,
        default_value="1280x720",
        allowed_values=tuple(PREVIEW_SIZES),
        restart_required=True,
        description="Preview resolution requested from rpicam-vid; applies when preview restarts.",
        group=_GROUP_PREVIEW,
        unit="px",
    ),
    CameraSettingCapability(
        identifier="still_width",
        label="Still width",
        value_type=CameraSettingType.INTEGER,
        default_value=STILL_WIDTH_MAXIMUM,
        minimum=320,
        maximum=STILL_WIDTH_MAXIMUM,
        step=2,
        description="Output width passed as --width. 4608 is the full Camera Module 3 sensor width.",
        group=_GROUP_IMAGE,
        unit="px",
        capture_only=True,
    ),
    CameraSettingCapability(
        identifier="still_height",
        label="Still height",
        value_type=CameraSettingType.INTEGER,
        default_value=STILL_HEIGHT_MAXIMUM,
        minimum=240,
        maximum=STILL_HEIGHT_MAXIMUM,
        step=2,
        description="Output height passed as --height. 2592 is the full Camera Module 3 sensor height.",
        group=_GROUP_IMAGE,
        unit="px",
        capture_only=True,
    ),
    CameraSettingCapability(
        identifier="jpeg_quality",
        label="JPEG quality",
        value_type=CameraSettingType.INTEGER,
        default_value=95,
        minimum=JPEG_QUALITY_MINIMUM,
        maximum=JPEG_QUALITY_MAXIMUM,
        step=1,
        description="JPEG quality for captured stills (--quality).",
        group=_GROUP_IMAGE,
        capture_only=True,
    ),
    _enum_setting(
        "denoise",
        "Denoise",
        DenoiseMode.CDN_HQ,
        _GROUP_IMAGE,
        "Noise reduction (--denoise). cdn_hq gives the strongest colour denoise for low-light stills.",
    ),
    _enum_setting(
        "hdr",
        "HDR",
        HdrMode.OFF,
        _GROUP_IMAGE,
        "High dynamic range (--hdr). May add latency, motion artefacts and exposure changes;"
        " only single-exp was observed to take effect on Camera Module 3 with rpicam-apps 1.14.",
    ),
    _enum_setting(
        "exposure_control",
        "Exposure control",
        ExposureControl.AUTO,
        _GROUP_EXPOSURE,
        "Automatic exposure omits --shutter and --gain. Manual fixes both and may cause"
        " under- or overexposure, noise or motion blur.",
    ),
    CameraSettingCapability(
        identifier="shutter_us",
        label="Shutter duration",
        value_type=CameraSettingType.INTEGER,
        default_value=16667,
        minimum=100,
        maximum=1_000_000,
        step=1,
        description="Fixed exposure time (--shutter), manual exposure only. Longer values"
        " brighten the image but blur moving subjects.",
        group=_GROUP_EXPOSURE,
        unit="µs",
        capture_only=True,
        active_when=_MANUAL_EXPOSURE,
    ),
    _float_setting(
        "gain",
        "Gain",
        4.0,
        1.0,
        16.0,
        0.1,
        _GROUP_EXPOSURE,
        "Fixed analogue gain (--gain), manual exposure only. Higher values brighten the image"
        " but add noise.",
        unit="×",
        active_when=_MANUAL_EXPOSURE,
    ),
    _enum_setting(
        "metering",
        "Metering",
        MeteringMode.CENTRE,
        _GROUP_EXPOSURE,
        "Region weighting used by automatic exposure (--metering).",
    ),
    _enum_setting(
        "exposure_mode",
        "Exposure mode",
        ExposureMode.NORMAL,
        _GROUP_EXPOSURE,
        "Automatic-exposure profile (--exposure); sport prefers shorter shutter times.",
    ),
    _float_setting(
        "ev",
        "EV compensation",
        0.3,
        -2.0,
        2.0,
        0.1,
        _GROUP_EXPOSURE,
        "Exposure compensation applied by automatic exposure (--ev); 0 means no change.",
        unit="EV",
    ),
    _enum_setting(
        "white_balance",
        "White balance",
        WhiteBalanceMode.AUTO,
        _GROUP_RENDERING,
        "Automatic white balance preset passed to rpicam-vid and rpicam-still (--awb).",
        capture_only=False,
    ),
    _float_setting(
        "brightness",
        "Brightness",
        0.0,
        -1.0,
        1.0,
        0.05,
        _GROUP_RENDERING,
        "Brightness offset applied after exposure (--brightness); 0 means no change.",
    ),
    _float_setting(
        "contrast",
        "Contrast",
        1.0,
        0.5,
        2.0,
        0.05,
        _GROUP_RENDERING,
        "Contrast multiplier (--contrast); 1.0 is normal.",
    ),
    _float_setting(
        "saturation",
        "Saturation",
        1.0,
        0.0,
        2.0,
        0.05,
        _GROUP_RENDERING,
        "Colour saturation (--saturation); 1.0 is normal and 0.0 is greyscale.",
    ),
    _float_setting(
        "sharpness",
        "Sharpness",
        1.1,
        0.1,
        2.0,
        0.05,
        _GROUP_RENDERING,
        "Sharpening strength (--sharpness); 1.0 is normal.",
    ),
    _enum_setting(
        "autofocus_mode",
        "Autofocus mode",
        AutofocusMode.AUTO,
        _GROUP_AUTOFOCUS,
        "auto scans when triggered; continuous refocuses continually; manual uses the lens"
        " position below (--autofocus-mode).",
    ),
    _enum_setting(
        "autofocus_range",
        "Autofocus range",
        AutofocusRange.NORMAL,
        _GROUP_AUTOFOCUS,
        "Focus distances scanned (--autofocus-range).",
        active_when=_AUTOMATIC_FOCUS,
    ),
    _enum_setting(
        "autofocus_speed",
        "Autofocus speed",
        AutofocusSpeed.FAST,
        _GROUP_AUTOFOCUS,
        "Lens movement speed while scanning (--autofocus-speed).",
        active_when=_AUTOMATIC_FOCUS,
    ),
    CameraSettingCapability(
        identifier="autofocus_on_capture",
        label="Autofocus on capture",
        value_type=CameraSettingType.BOOLEAN,
        default_value=True,
        description="Run an autofocus scan immediately before the still (--autofocus-on-capture)."
        " Adds roughly half a second of capture latency.",
        group=_GROUP_AUTOFOCUS,
        capture_only=True,
        active_when=_AUTOMATIC_FOCUS,
    ),
    _float_setting(
        "autofocus_window_x",
        "Autofocus window left",
        0.2,
        0.0,
        1.0,
        0.01,
        _GROUP_AUTOFOCUS,
        "Left edge of the focus region as a fraction of image width (0 = left).",
        active_when=_AUTOMATIC_FOCUS,
    ),
    _float_setting(
        "autofocus_window_y",
        "Autofocus window top",
        0.15,
        0.0,
        1.0,
        0.01,
        _GROUP_AUTOFOCUS,
        "Top edge of the focus region as a fraction of image height (0 = top).",
        active_when=_AUTOMATIC_FOCUS,
    ),
    _float_setting(
        "autofocus_window_width",
        "Autofocus window width",
        0.6,
        0.01,
        1.0,
        0.01,
        _GROUP_AUTOFOCUS,
        "Width of the focus region as a fraction of image width; left + width must not exceed 1.",
        active_when=_AUTOMATIC_FOCUS,
    ),
    _float_setting(
        "autofocus_window_height",
        "Autofocus window height",
        0.7,
        0.01,
        1.0,
        0.01,
        _GROUP_AUTOFOCUS,
        "Height of the focus region as a fraction of image height; top + height must not exceed 1.",
        active_when=_AUTOMATIC_FOCUS,
    ),
    _float_setting(
        "lens_position",
        "Manual lens position",
        1.0,
        0.0,
        15.0,
        0.05,
        _GROUP_AUTOFOCUS,
        "Fixed focus (--lens-position), manual autofocus mode only. Reciprocal distance:"
        " 0 is infinity, 1.0 is 1 m, 0.5 is 2 m.",
        unit="dioptres",
        active_when=_MANUAL_FOCUS,
    ),
    CameraSettingCapability(
        identifier="verbosity",
        label="rpicam verbosity",
        value_type=CameraSettingType.INTEGER,
        default_value=2,
        minimum=0,
        maximum=2,
        step=1,
        description="rpicam-still log level (--verbose): 0 silent, 1 normal, 2 verbose."
        " Only the stderr tail is kept, and only after a failure.",
        group=_GROUP_DIAGNOSTICS,
        capture_only=True,
    ),
    CameraSettingCapability(
        identifier=LAST_STILL_COMMAND,
        label="Last still command",
        value_type=CameraSettingType.STRING,
        default_value="",
        read_only=True,
        description="Arguments emitted for the most recent rpicam-still run and its exit status."
        " A successful exit confirms rpicam accepted the arguments, not their visual effect.",
        group=_GROUP_DIAGNOSTICS,
    ),
)
_CAPABILITY_BY_ID: Final = {item.identifier: item for item in BASE_CAPABILITIES}


@dataclass(frozen=True)
class RpicamSettings:
    """Hold the allowlisted rpicam options applied to each launched command.

    Field names equal capability identifiers. Construction validates every
    field against its capability bounds and enum allowlist, so an instance
    never carries an out-of-range single value. Rules spanning several
    fields (currently the autofocus window) are checked by :meth:`validate`
    so that a multi-field update may pass through intermediate states.

    Inactive values are retained rather than rejected: shutter and gain are
    stored but only emitted in manual exposure, the lens position only in
    manual autofocus, and autofocus range/speed/window/on-capture only in
    automatic or continuous autofocus. This keeps an administrator's values
    when switching modes without ever emitting conflicting arguments.
    """

    preview_size: str = "1280x720"
    still_width: int = STILL_WIDTH_MAXIMUM
    still_height: int = STILL_HEIGHT_MAXIMUM
    jpeg_quality: int = 95
    denoise: DenoiseMode = DenoiseMode.CDN_HQ
    hdr: HdrMode = HdrMode.OFF
    exposure_control: ExposureControl = ExposureControl.AUTO
    shutter_us: int = 16667
    gain: float = 4.0
    metering: MeteringMode = MeteringMode.CENTRE
    exposure_mode: ExposureMode = ExposureMode.NORMAL
    ev: float = 0.3
    white_balance: WhiteBalanceMode = WhiteBalanceMode.AUTO
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.1
    autofocus_mode: AutofocusMode = AutofocusMode.AUTO
    autofocus_range: AutofocusRange = AutofocusRange.NORMAL
    autofocus_speed: AutofocusSpeed = AutofocusSpeed.FAST
    autofocus_on_capture: bool = True
    autofocus_window_x: float = 0.2
    autofocus_window_y: float = 0.15
    autofocus_window_width: float = 0.6
    autofocus_window_height: float = 0.7
    lens_position: float = 1.0
    verbosity: int = 2

    def __post_init__(self) -> None:
        """Validate each field against its declared capability; raise ``ValueError``."""
        for capability in BASE_CAPABILITIES:
            if capability.read_only:
                continue
            identifier = capability.identifier
            enum_type = _ENUM_FIELDS.get(identifier)
            raw = getattr(self, identifier)
            if enum_type is not None and not isinstance(raw, enum_type):
                raise ValueError(f"{identifier} must be a {enum_type.__name__}")
            validate_camera_setting(capability, self.requested_value(identifier))

    @property
    def preview_dimensions(self) -> tuple[int, int]:
        """Return the (width, height) pair requested from rpicam-vid."""
        return PREVIEW_SIZES[self.preview_size]

    @property
    def autofocus_window(self) -> NormalizedRectangle:
        """Return the autofocus window as a typed rectangle.

        Raises ``ValueError`` prefixed with the offending ``autofocus_window_*``
        identifier when the components do not form an in-frame rectangle.
        """
        try:
            return NormalizedRectangle(
                self.autofocus_window_x,
                self.autofocus_window_y,
                self.autofocus_window_width,
                self.autofocus_window_height,
            )
        except ValueError as error:
            raise ValueError(f"autofocus_window_{error}") from error

    @property
    def manual_exposure(self) -> bool:
        """Return whether shutter and gain must be emitted."""
        return self.exposure_control is ExposureControl.MANUAL

    @property
    def manual_focus(self) -> bool:
        """Return whether the fixed lens position replaces autofocus arguments."""
        return self.autofocus_mode is AutofocusMode.MANUAL

    @property
    def scans_on_capture(self) -> bool:
        """Return whether ``--autofocus-on-capture`` is emitted for the still."""
        return self.autofocus_on_capture and not self.manual_focus

    def validate(self) -> None:
        """Check rules spanning several fields; raise ``ValueError`` naming a field."""
        _ = self.autofocus_window

    def requested_value(self, identifier: str) -> CameraSettingValue:
        """Return a field as the scalar persisted in configuration (enums as strings)."""
        value: object = getattr(self, identifier)
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, bool | int | float | str):
            return value
        raise TypeError(f"{identifier} is not a scalar setting")

    def with_setting(self, setting: ValidatedCameraSetting) -> "RpicamSettings":
        """Return a copy with one validated setting replaced.

        Enum strings are converted to their enum member. Unknown or read-only
        identifiers raise ``ValueError``; cross-field rules are not checked.
        """
        identifier = setting.identifier
        capability = _CAPABILITY_BY_ID.get(identifier)
        if capability is None or capability.read_only:
            raise ValueError(f"{identifier} is not a writable rpicam setting")
        value = setting.value
        enum_type = _ENUM_FIELDS.get(identifier)
        converted: object
        if enum_type is not None:
            converted = enum_type(value)
        elif identifier in _INTEGER_FIELDS:
            converted = int(value)
        elif identifier in _BOOLEAN_FIELDS:
            converted = bool(value)
        elif identifier == "preview_size":
            converted = str(value)
        else:
            converted = float(value)
        return replace(self, **{identifier: converted})


def capabilities_for(
    settings: RpicamSettings, last_still_command: str | None
) -> tuple[CameraSettingCapability, ...]:
    """Return declarations carrying the current requested values.

    Effective values are not reported for camera controls because rpicam only
    confirms that it accepted an argument. The read-only last-command entry
    reports the most recent emitted arguments and exit status, if any.
    """
    declared: list[CameraSettingCapability] = []
    for capability in BASE_CAPABILITIES:
        if capability.identifier == LAST_STILL_COMMAND:
            declared.append(replace(capability, effective_value=last_still_command))
        else:
            declared.append(
                replace(
                    capability,
                    requested_value=settings.requested_value(capability.identifier),
                )
            )
    return tuple(declared)


def settings_from_mapping(
    base: RpicamSettings, requested: Mapping[str, CameraSettingValue]
) -> RpicamSettings:
    """Apply known persisted requests to ``base`` and enforce cross-field rules.

    Unknown identifiers are ignored so other backends' settings survive.
    Read-only, invalid, or inconsistent values raise ``ValueError`` whose
    message starts with the setting identifier; ``base`` is never modified.
    """
    candidate = base
    for identifier, value in requested.items():
        capability = _CAPABILITY_BY_ID.get(identifier)
        if capability is None:
            continue
        if capability.read_only:
            raise ValueError(f"{identifier} is read-only")
        candidate = candidate.with_setting(validate_camera_setting(capability, value))
    candidate.validate()
    return candidate
