"""Expose the hardware-independent camera contract to application code."""

from photobooth.camera.contract import (
    CameraBackend,
    CameraError,
    CameraOperationError,
    CameraUnavailableError,
)
from photobooth.camera.opencv import OpenCVCameraBackend
from photobooth.camera.synthetic import SyntheticCameraBackend

__all__ = [
    "CameraBackend",
    "CameraError",
    "CameraOperationError",
    "CameraUnavailableError",
    "OpenCVCameraBackend",
    "SyntheticCameraBackend",
]