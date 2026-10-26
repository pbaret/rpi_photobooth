"""Define backend-declared camera controls and their validated values.

Capabilities belong to a concrete camera backend; persisted configuration
does not make an unsupported control available or imply that a request took
effect. Effective values are reported separately by the active backend.
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import TypeAlias


CameraSettingValue: TypeAlias = bool | int | float | str


class CameraSettingType(str, Enum):
    """Describe the native value shape used to render and validate a control."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"


@dataclass(frozen=True)
class CameraSettingCapability:
    """Describe one control the owning backend explicitly supports.

    ``requested_value`` is the backend's configured request, while
    ``effective_value`` is a value actually applied or reported by that
    backend. A missing effective value means the backend cannot currently
    report it. Read-only controls cannot be submitted, and restart-required
    controls are persisted without being applied to the active backend.
    """

    identifier: str
    label: str
    value_type: CameraSettingType
    default_value: CameraSettingValue
    requested_value: CameraSettingValue | None = None
    effective_value: CameraSettingValue | None = None
    allowed_values: tuple[CameraSettingValue, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    read_only: bool = False
    restart_required: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        """Reject malformed declarations before they reach application code."""
        if not self.identifier or not self.label:
            raise ValueError("camera setting identifier and label must not be empty")
        if self.value_type is CameraSettingType.ENUM and not self.allowed_values:
            raise ValueError("enum camera settings must declare allowed values")
        if self.value_type is CameraSettingType.ENUM and any(
            not isinstance(value, str) for value in self.allowed_values
        ):
            raise ValueError("enum camera setting values must be strings")
        if self.value_type is not CameraSettingType.ENUM and self.allowed_values:
            raise ValueError("only enum camera settings may declare allowed values")
        numeric_constraints = (self.minimum, self.maximum, self.step)
        if self.value_type not in {CameraSettingType.INTEGER, CameraSettingType.FLOAT}:
            if any(value is not None for value in numeric_constraints):
                raise ValueError("numeric constraints require a numeric camera setting")
        elif any(
            value is not None
            and (type(value) not in {int, float} or not math.isfinite(float(value)))
            for value in numeric_constraints
        ):
            raise ValueError("numeric camera constraints must be finite numbers")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("camera setting minimum must not exceed maximum")
        if self.step is not None and self.step <= 0:
            raise ValueError("camera setting step must be positive")
        validate_camera_setting(self, self.default_value)
        if self.requested_value is not None:
            validate_camera_setting(self, self.requested_value)
        if self.effective_value is not None:
            validate_camera_setting(self, self.effective_value)


@dataclass(frozen=True)
class ValidatedCameraSetting:
    """Hold a requested value only after capability validation succeeds."""

    identifier: str
    value: CameraSettingValue


def validate_camera_setting(
    capability: CameraSettingCapability,
    value: CameraSettingValue,
) -> ValidatedCameraSetting:
    """Validate a value's exact type and constraints against one declaration.

    Booleans are not accepted as integers, numeric bounds and steps are
    enforced, and enum membership is exact. Read-only status is enforced by
    callers because backends still need to declare their default/readback.
    """
    value_type = capability.value_type
    valid_type = (
        (value_type is CameraSettingType.BOOLEAN and type(value) is bool)
        or (value_type is CameraSettingType.INTEGER and type(value) is int)
        or (
            value_type is CameraSettingType.FLOAT
            and type(value) in {int, float}
            and math.isfinite(float(value))
        )
        or (
            value_type in {CameraSettingType.STRING, CameraSettingType.ENUM}
            and isinstance(value, str)
        )
    )
    if not valid_type:
        raise ValueError(f"{capability.identifier} has an invalid value type")
    if value_type is CameraSettingType.ENUM and value not in capability.allowed_values:
        raise ValueError(f"{capability.identifier} must be one of its declared values")
    if value_type in {CameraSettingType.INTEGER, CameraSettingType.FLOAT}:
        numeric_value = float(value)
        if capability.minimum is not None and numeric_value < capability.minimum:
            raise ValueError(f"{capability.identifier} is below its minimum")
        if capability.maximum is not None and numeric_value > capability.maximum:
            raise ValueError(f"{capability.identifier} is above its maximum")
        if capability.step is not None:
            origin = capability.minimum if capability.minimum is not None else 0
            increments = (numeric_value - origin) / capability.step
            if not math.isclose(increments, round(increments), abs_tol=1e-9):
                raise ValueError(f"{capability.identifier} does not match its step")
    normalized_value = float(value) if value_type is CameraSettingType.FLOAT else value
    return ValidatedCameraSetting(capability.identifier, normalized_value)