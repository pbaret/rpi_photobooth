"""Expose the hardware-independent camera contract to application code."""

from photobooth.camera.contract import (
    CameraBackend,
    CameraError,
    CameraOperationError,
    CameraUnavailableError,
)
from photobooth.camera.opencv import OpenCVCameraBackend
from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingType,
    CameraSettingValue,
    ValidatedCameraSetting,
    validate_camera_setting,
)
from photobooth.camera.synthetic import SyntheticCameraBackend

__all__ = [
    "CameraBackend",
    "CameraError",
    "CameraOperationError",
    "CameraUnavailableError",
    "CameraSettingCapability",
    "CameraSettingType",
    "CameraSettingValue",
    "OpenCVCameraBackend",
    "SyntheticCameraBackend",
    "ValidatedCameraSetting",
    "validate_camera_setting",
]