"""Define validated print settings and their stable configuration values."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import TypeVar


class PrintSettingsError(ValueError):
    """Report a print setting that is malformed or outside the supported profile."""


class PrinterBackendKind(str, Enum):
    """Select a development no-op or the operating-system CUPS backend."""

    NULL = "null"
    CUPS = "cups"


class PageSize(str, Enum):
    """Represent supported page sizes reported for the validated CP1000 queue."""

    POSTCARD = "Postcard"


class ColorModel(str, Enum):
    """Represent the supported CUPS color model."""

    RGB = "RGB"


class Resolution(str, Enum):
    """Represent the supported printer resolution."""

    DPI_300 = "300dpi"


class ImageType(str, Enum):
    """Represent the supported Gutenprint image rendering type."""

    PHOTO = "Photo"


class PageFit(str, Enum):
    """Choose whether an image shrinks, crops, or expands to fit the page."""

    SHRINK = "Shrink"
    CROP = "Crop"
    EXPAND = "Expand"


class ColorPrecision(str, Enum):
    """Select the supported Gutenprint color precision."""

    NORMAL = "Normal"
    BEST = "Best"


class ColorCorrection(str, Enum):
    """Select a color correction mode explicitly supported by this application."""

    NONE = "None"
    ACCURATE = "Accurate"
    BRIGHT = "Bright"
    HUE = "Hue"
    UNCORRECTED = "Uncorrected"
    DESATURATED = "Desaturated"


_QUEUE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\Z")
_EnumT = TypeVar("_EnumT", bound=Enum)
_ADJUSTMENT_STEPS: dict[str, frozenset[int]] = {
    "brightness": frozenset((*range(0, 1000, 100), *range(1100, 2001, 100))),
    "contrast": frozenset((*range(0, 1000, 100), *range(1100, 4001, 100))),
    "saturation": frozenset((*range(0, 1000, 100), *range(1100, 9001, 100))),
    "gamma": frozenset(range(100, 4001, 100)),
}


@dataclass(frozen=True)
class PrintingSettings:
    """Hold the user-configurable printer backend and allowlisted print profile.

    Adjustment values are the discrete driver integers reported by the
    validated Canon CP1000 Gutenprint queue. Python ``None`` means neutral;
    the CUPS mapper deliberately sends the driver's literal ``None`` value.
    """

    enabled: bool = True
    backend: PrinterBackendKind = PrinterBackendKind.NULL
    queue_name: str = ""
    page_size: PageSize = PageSize.POSTCARD
    color_model: ColorModel = ColorModel.RGB
    resolution: Resolution = Resolution.DPI_300
    image_type: ImageType = ImageType.PHOTO
    borderless: bool = True
    page_fit: PageFit = PageFit.SHRINK
    color_precision: ColorPrecision = ColorPrecision.NORMAL
    color_correction: ColorCorrection = ColorCorrection.NONE
    legacy_dyesub_gamma: bool = False
    brightness: int | None = None
    contrast: int | None = None
    saturation: int | None = None
    gamma: int | None = None

    def __post_init__(self) -> None:
        """Reject invalid booleans, queue names, enum values, and adjustments."""
        if type(self.enabled) is not bool:
            raise PrintSettingsError("printing_enabled must be a boolean")
        if type(self.backend) is not PrinterBackendKind:
            raise PrintSettingsError("printer_backend must be supported")
        if type(self.queue_name) is not str:
            raise PrintSettingsError("cups_printer_name must be a string")
        if self.queue_name and _QUEUE_NAME_PATTERN.fullmatch(self.queue_name) is None:
            raise PrintSettingsError("cups_printer_name is not a safe CUPS queue name")
        for field_name, enum_type in (
            ("page_size", PageSize),
            ("color_model", ColorModel),
            ("resolution", Resolution),
            ("image_type", ImageType),
            ("page_fit", PageFit),
            ("color_precision", ColorPrecision),
            ("color_correction", ColorCorrection),
        ):
            if not isinstance(getattr(self, field_name), enum_type):
                raise PrintSettingsError(f"{field_name} is not supported")
        if type(self.borderless) is not bool or type(self.legacy_dyesub_gamma) is not bool:
            raise PrintSettingsError("printer boolean options must be booleans")
        for field_name, choices in _ADJUSTMENT_STEPS.items():
            value = getattr(self, field_name)
            if value is not None and (
                type(value) is not int or value not in choices
            ):
                raise PrintSettingsError(f"{field_name} is not a supported driver value")

    def to_mapping(self) -> dict[str, object]:
        """Return JSON-compatible stable driver values, not translated labels."""
        return {
            "enabled": self.enabled,
            "backend": self.backend.value,
            "queue_name": self.queue_name,
            "page_size": self.page_size.value,
            "color_model": self.color_model.value,
            "resolution": self.resolution.value,
            "image_type": self.image_type.value,
            "borderless": self.borderless,
            "page_fit": self.page_fit.value,
            "color_precision": self.color_precision.value,
            "color_correction": self.color_correction.value,
            "legacy_dyesub_gamma": self.legacy_dyesub_gamma,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "gamma": self.gamma,
        }


def printing_settings_from_mapping(values: Mapping[str, object]) -> PrintingSettings:
    """Decode a strict JSON/form-value map into validated print settings."""
    supported = {
        "enabled",
        "backend",
        "queue_name",
        "page_size",
        "color_model",
        "resolution",
        "image_type",
        "borderless",
        "page_fit",
        "color_precision",
        "color_correction",
        "legacy_dyesub_gamma",
        "brightness",
        "contrast",
        "saturation",
        "gamma",
    }
    unknown = set(values) - supported
    if unknown:
        raise PrintSettingsError(f"unknown printing setting: {sorted(unknown)[0]}")

    def string_value(name: str, default: str) -> str:
        """Read a string-valued field or its default from the supplied mapping."""
        value = values.get(name, default)
        if not isinstance(value, str):
            raise PrintSettingsError(f"{name} must be a string")
        return value

    def boolean_value(name: str, default: bool) -> bool:
        """Read a JSON boolean without accepting integers as booleans."""
        value = values.get(name, default)
        if type(value) is not bool:
            raise PrintSettingsError(f"{name} must be a boolean")
        return value

    def enum_value(name: str, enum_type: type[_EnumT], default: str) -> _EnumT:
        """Resolve one stable enum value and report malformed choices."""
        raw_value = string_value(name, default)
        try:
            return enum_type(raw_value)
        except ValueError as error:
            raise PrintSettingsError(f"{name} is not supported") from error

    def adjustment_value(name: str) -> int | None:
        """Read an optional discrete driver integer, rejecting booleans."""
        value = values.get(name)
        if value is not None and type(value) is not int:
            raise PrintSettingsError(f"{name} must be an integer or null")
        return value

    backend = enum_value("backend", PrinterBackendKind, PrinterBackendKind.NULL.value)
    page_size = enum_value("page_size", PageSize, PageSize.POSTCARD.value)
    color_model = enum_value("color_model", ColorModel, ColorModel.RGB.value)
    resolution = enum_value("resolution", Resolution, Resolution.DPI_300.value)
    image_type = enum_value("image_type", ImageType, ImageType.PHOTO.value)
    page_fit = enum_value("page_fit", PageFit, PageFit.SHRINK.value)
    color_precision = enum_value(
        "color_precision", ColorPrecision, ColorPrecision.NORMAL.value
    )
    color_correction = enum_value(
        "color_correction", ColorCorrection, ColorCorrection.NONE.value
    )
    return PrintingSettings(
        enabled=boolean_value("enabled", True),
        backend=backend,
        queue_name=string_value("queue_name", ""),
        page_size=page_size,
        color_model=color_model,
        resolution=resolution,
        image_type=image_type,
        borderless=boolean_value("borderless", True),
        page_fit=page_fit,
        color_precision=color_precision,
        color_correction=color_correction,
        legacy_dyesub_gamma=boolean_value("legacy_dyesub_gamma", False),
        brightness=adjustment_value("brightness"),
        contrast=adjustment_value("contrast"),
        saturation=adjustment_value("saturation"),
        gamma=adjustment_value("gamma"),
    )


def supported_adjustments(name: str) -> tuple[int, ...]:
    """Return the queue-validated discrete values for one color control."""
    choices = _ADJUSTMENT_STEPS.get(name)
    if choices is None:
        raise PrintSettingsError(f"{name} is not a supported color control")
    return tuple(sorted(choices))
