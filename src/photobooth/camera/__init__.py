"""Expose the hardware-independent camera contract to application code."""

from photobooth.camera.contract import (
    CameraBackend,
    CameraError,
    CameraOperationError,
    CameraUnavailableError,
)

__all__ = [
    "CameraBackend",
    "CameraError",
    "CameraOperationError",
    "CameraUnavailableError",
]