"""Implement CameraBackend using a locally attached OpenCV webcam.

OpenCV owns the device handle for the duration of preview. The backend keeps
OpenCV and image-array details behind the hardware-independent camera contract.
OpenCV's Python image-array boundary is untyped, so Any is localized to calls
into that library; application-facing values remain precisely typed.
"""

from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, cast

import cv2

from photobooth.camera.contract import CameraOperationError, CameraUnavailableError
from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingType,
    CameraSettingValue,
    ValidatedCameraSetting,
    validate_camera_setting,
)


class _CaptureHandle(Protocol):
    """Describe the small VideoCapture surface owned by this backend."""

    def isOpened(self) -> bool:
        """Return whether the device was successfully acquired."""
        ...

    def set(self, property_id: int, value: float) -> bool:
        """Request a camera property value."""
        ...

    def get(self, property_id: int) -> float:
        """Return the device's current property value."""
        ...

    def read(self) -> tuple[bool, object]:
        """Return whether a frame was read and its opaque image value."""
        ...

    def release(self) -> None:
        """Release the device handle."""
        ...


class _EncodedImage(Protocol):
    """Describe the encoded image buffer returned by OpenCV."""

    def tobytes(self) -> bytes:
        """Return the image buffer as immutable bytes."""
        ...


class OpenCVCameraBackend:
    """Own one OpenCV webcam and serialize all access to its handle.

    The default device is webcam index 0 and its requested frame size is
    640-by-480. Drivers may negotiate a different effective size. Preview is
    horizontally mirrored for a selfie view; captured stills retain the raw,
    unmirrored camera orientation. The browser is responsible for display.
    """

    def __init__(
        self,
        camera_index: int = 0,
        requested_width: int = 640,
        requested_height: int = 480,
        mirror_preview: bool = True,
    ) -> None:
        """Configure device selection and dimensions without opening it."""
        if camera_index < 0:
            raise ValueError("camera_index must not be negative")
        if requested_width < 1 or requested_height < 1:
            raise ValueError("requested dimensions must be positive")
        self._camera_index = camera_index
        self._requested_width = requested_width
        self._requested_height = requested_height
        self._mirror_preview = mirror_preview
        self._capture: _CaptureHandle | None = None
        self._effective_resolution: tuple[int, int] | None = None
        self._lock = Lock()

    @property
    def requested_resolution(self) -> tuple[int, int]:
        """Return the width and height requested from the webcam driver."""
        return self._requested_width, self._requested_height

    @property
    def effective_resolution(self) -> tuple[int, int] | None:
        """Return driver-reported dimensions while the camera is started."""
        with self._lock:
            return self._effective_resolution

    def get_capabilities(self) -> tuple[CameraSettingCapability, ...]:
        """Declare implemented resolution requests and software preview mirroring.

        OpenCV does not provide portable generic camera controls here. The
        resolution values are driver requests with readback only while the
        camera is active; mirroring is an application-side preview operation.
        """
        with self._lock:
            return self._capabilities_locked()

    def configure_settings(
        self, settings: Mapping[str, CameraSettingValue]
    ) -> None:
        """Load supported persisted requests without treating unknown keys as valid."""
        with self._lock:
            capabilities = {item.identifier: item for item in self._capabilities_locked()}
            for identifier, value in settings.items():
                capability = capabilities.get(identifier)
                if capability is None:
                    continue
                validated = validate_camera_setting(capability, value)
                self._store_setting_locked(validated)

    def apply_setting(self, setting: ValidatedCameraSetting) -> CameraSettingValue:
        """Apply software mirroring immediately; resolution awaits camera restart."""
        with self._lock:
            capabilities = {item.identifier: item for item in self._capabilities_locked()}
            capability = capabilities.get(setting.identifier)
            if capability is None:
                raise ValueError(f"{setting.identifier} is unsupported")
            if capability.read_only or capability.restart_required:
                raise ValueError(f"{setting.identifier} cannot be applied without restart")
            validated = validate_camera_setting(capability, setting.value)
            self._store_setting_locked(validated)
            return validated.value

    def _capabilities_locked(self) -> tuple[CameraSettingCapability, ...]:
        """Build control declarations while the caller holds the backend lock."""
        effective = self._effective_resolution
        return (
            CameraSettingCapability(
                identifier="preview_width",
                label="Preview width",
                value_type=CameraSettingType.INTEGER,
                default_value=640,
                requested_value=self._requested_width,
                effective_value=effective[0] if effective is not None else None,
                minimum=1,
                maximum=8192,
                step=1,
                restart_required=True,
                description="Requested webcam frame width; the driver may negotiate another value.",
            ),
            CameraSettingCapability(
                identifier="preview_height",
                label="Preview height",
                value_type=CameraSettingType.INTEGER,
                default_value=480,
                requested_value=self._requested_height,
                effective_value=effective[1] if effective is not None else None,
                minimum=1,
                maximum=8192,
                step=1,
                restart_required=True,
                description="Requested webcam frame height; the driver may negotiate another value.",
            ),
            CameraSettingCapability(
                identifier="preview_mirror",
                label="Mirror preview",
                value_type=CameraSettingType.BOOLEAN,
                default_value=True,
                requested_value=self._mirror_preview,
                effective_value=self._mirror_preview,
                description="Mirror preview frames without changing captured stills.",
            ),
        )

    def _store_setting_locked(self, setting: ValidatedCameraSetting) -> None:
        """Store the backend option after capability validation."""
        if setting.identifier == "preview_width":
            self._requested_width = int(setting.value)
        elif setting.identifier == "preview_height":
            self._requested_height = int(setting.value)
        elif setting.identifier == "preview_mirror":
            self._mirror_preview = bool(setting.value)

    def start(self) -> None:
        """Acquire the webcam once and request the configured frame dimensions.

        A missing or busy device raises CameraUnavailableError. Other OpenCV
        failures raise CameraOperationError. Failed startup attempts release
        any handle acquired during the attempt.
        """
        with self._lock:
            if self._capture is not None:
                return
            try:
                opencv: Any = cv2
                capture = cast(_CaptureHandle, opencv.VideoCapture(self._camera_index))
                self._capture = capture
                if not capture.isOpened():
                    self._stop_locked()
                    raise CameraUnavailableError(
                        f"webcam index {self._camera_index} is unavailable or busy"
                    )
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._requested_width))
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._requested_height))
                self._effective_resolution = (
                    int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))),
                    int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))),
                )
            except CameraUnavailableError:
                raise
            except Exception as error:
                self._stop_locked()
                raise CameraOperationError("webcam startup failed") from error

    def stop(self) -> None:
        """Release the webcam; repeated stops are harmless.

        If the driver raises while releasing, the error is translated and the
        handle remains owned so a caller can retry cleanup.
        """
        with self._lock:
            self._stop_locked()

    def preview_frame(self) -> bytes:
        """Read and JPEG-encode one mirrored preview frame.

        A failed read or encode stops the backend and raises
        CameraOperationError. The camera remains owned after a successful read.
        """
        with self._lock:
            capture = self._require_started()
            try:
                opencv: Any = cv2
                read_succeeded, frame = capture.read()
                if not read_succeeded:
                    raise CameraOperationError("webcam did not provide a preview frame")
                if self._mirror_preview:
                    frame = opencv.flip(frame, 1)
                encode_succeeded, encoded = opencv.imencode(".jpg", frame)
                if not encode_succeeded:
                    raise CameraOperationError("preview frame could not be encoded")
                encoded_image = cast(_EncodedImage, encoded)
                return encoded_image.tobytes()
            except Exception as error:
                self._stop_locked()
                if isinstance(error, CameraOperationError):
                    raise
                raise CameraOperationError("webcam preview failed") from error

    def capture(self, output_path: Path) -> None:
        """Write one unmirrored JPEG still and release the webcam for review.

        The output path remains caller-owned. Read, encode, or write failures
        attempt to release the device and raise CameraOperationError.
        """
        with self._lock:
            capture = self._require_started()
            try:
                opencv: Any = cv2
                read_succeeded, frame = capture.read()
                if not read_succeeded:
                    raise CameraOperationError("webcam did not provide a capture frame")
                encode_succeeded, encoded = opencv.imencode(".jpg", frame)
                if not encode_succeeded:
                    raise CameraOperationError("capture frame could not be encoded")
                encoded_image = cast(_EncodedImage, encoded)
                output_path.write_bytes(encoded_image.tobytes())
            except Exception as error:
                self._stop_locked()
                if isinstance(error, CameraOperationError):
                    raise
                raise CameraOperationError("webcam capture failed") from error
            self._stop_locked()

    def _require_started(self) -> _CaptureHandle:
        """Return the owned handle or report that preview is not active."""
        if self._capture is None:
            raise CameraUnavailableError("camera is not started")
        return self._capture

    def _stop_locked(self) -> None:
        """Release the handle while the caller holds the backend lock."""
        capture = self._capture
        if capture is None:
            self._effective_resolution = None
            return
        try:
            capture.release()
        except Exception as error:
            raise CameraOperationError("webcam could not be released") from error
        self._capture = None
        self._effective_resolution = None