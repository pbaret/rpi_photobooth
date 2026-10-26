"""Provide a deterministic, hardware-free implementation of CameraBackend.

The backend is intended for automated tests and development of application
workflows that need camera-shaped JPEG data without acquiring a device.
"""

from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image, ImageDraw

from photobooth.camera.contract import CameraOperationError, CameraUnavailableError
from photobooth.camera.settings import (
    CameraSettingCapability,
    CameraSettingType,
    CameraSettingValue,
    ValidatedCameraSetting,
    validate_camera_setting,
)


class SyntheticCameraBackend:
    """Generate fixed JPEG content while emulating camera lifecycle behavior.

    No device or external process is owned. Operations on one instance are
    serialized, and successful capture stops the backend for review just like
    hardware backends.
    """

    def __init__(self) -> None:
        """Create a stopped backend with no external resources to acquire."""
        self._started = False
        self._lock = Lock()
        self._overlay_enabled = True
        self._jpeg_quality = 85
        self._scene = "classic"
        self._requested_scene = "classic"

    def get_capabilities(self) -> tuple[CameraSettingCapability, ...]:
        """Describe synthetic-only test controls and their currently effective values.

        These declarations are useful for exercising admin behavior and are
        not claims about connected camera hardware.
        """
        with self._lock:
            return self._capabilities_locked()

    def configure_settings(
        self, settings: Mapping[str, CameraSettingValue]
    ) -> None:
        """Load supported saved requests while preserving ignored backend keys."""
        with self._lock:
            capabilities = {item.identifier: item for item in self._capabilities_locked()}
            for identifier, value in settings.items():
                capability = capabilities.get(identifier)
                if capability is None:
                    continue
                if capability.read_only:
                    raise ValueError(f"{identifier} is read-only")
                validated = validate_camera_setting(capability, value)
                self._store_setting_locked(validated)

    def apply_setting(self, setting: ValidatedCameraSetting) -> CameraSettingValue:
        """Apply a writable live synthetic control and return its effective value."""
        with self._lock:
            capabilities = {item.identifier: item for item in self._capabilities_locked()}
            capability = capabilities.get(setting.identifier)
            if capability is None:
                raise ValueError(f"{setting.identifier} is unsupported")
            if capability.read_only:
                raise ValueError(f"{setting.identifier} is read-only")
            if capability.restart_required:
                raise ValueError(f"{setting.identifier} cannot be applied without restart")
            validated = validate_camera_setting(capability, setting.value)
            self._store_setting_locked(validated)
            return validated.value

    def start(self) -> None:
        """Make preview available; repeated calls leave the backend started."""
        with self._lock:
            self._scene = self._requested_scene
            self._started = True

    def stop(self) -> None:
        """Stop preview; repeated calls are harmless because no device is owned."""
        with self._lock:
            self._started = False

    def preview_frame(self) -> bytes:
        """Return deterministic JPEG bytes or fail if preview is stopped.

        Rendering failures are translated to CameraOperationError and leave
        the backend stopped, matching the camera contract's cleanup behavior.
        """
        with self._lock:
            self._require_started()
            try:
                return self._render_jpeg(
                    self._overlay_enabled, self._jpeg_quality, self._scene
                )
            except CameraOperationError:
                self._started = False
                raise

    def capture(self, output_path: Path) -> None:
        """Write a deterministic JPEG still and stop, including on write failure.

        The caller retains ownership of output_path and any partial file left
        by a failed write.
        """
        with self._lock:
            self._require_started()
            try:
                output_path.write_bytes(
                    self._render_jpeg(
                        self._overlay_enabled, self._jpeg_quality, self._scene
                    )
                )
            except CameraOperationError:
                raise
            except OSError as error:
                raise CameraOperationError("capture output could not be written") from error
            finally:
                self._started = False

    def _require_started(self) -> None:
        """Reject operations that require preview when the backend is stopped."""
        if not self._started:
            raise CameraUnavailableError("camera is not started")

    def _capabilities_locked(self) -> tuple[CameraSettingCapability, ...]:
        """Build capability readbacks while the caller owns the backend lock."""
        return (
            CameraSettingCapability(
                identifier="synthetic_overlay",
                label="Synthetic overlay",
                value_type=CameraSettingType.BOOLEAN,
                default_value=True,
                requested_value=self._overlay_enabled,
                effective_value=self._overlay_enabled,
                description="Show the synthetic scene label in generated frames.",
            ),
            CameraSettingCapability(
                identifier="synthetic_quality",
                label="Synthetic JPEG quality",
                value_type=CameraSettingType.INTEGER,
                default_value=85,
                requested_value=self._jpeg_quality,
                effective_value=self._jpeg_quality,
                minimum=30,
                maximum=95,
                step=5,
                description="JPEG quality used for generated test frames.",
            ),
            CameraSettingCapability(
                identifier="synthetic_scene",
                label="Synthetic scene",
                value_type=CameraSettingType.ENUM,
                default_value="classic",
                requested_value=self._requested_scene,
                effective_value=self._scene,
                allowed_values=("classic", "colorful"),
                restart_required=True,
                description="Scene palette used after restarting the application.",
            ),
            CameraSettingCapability(
                identifier="synthetic_running",
                label="Synthetic preview running",
                value_type=CameraSettingType.BOOLEAN,
                default_value=False,
                effective_value=self._started,
                read_only=True,
                description="Whether this synthetic backend currently has preview active.",
            ),
        )

    def _store_setting_locked(self, setting: ValidatedCameraSetting) -> None:
        """Store one previously validated setting while holding the lock."""
        if setting.identifier == "synthetic_overlay":
            self._overlay_enabled = bool(setting.value)
        elif setting.identifier == "synthetic_quality":
            self._jpeg_quality = int(setting.value)
        elif setting.identifier == "synthetic_scene":
            self._requested_scene = str(setting.value)

    @staticmethod
    def _render_jpeg(overlay_enabled: bool, quality: int, scene: str) -> bytes:
        """Render a fixed synthetic test scene as a JPEG image."""
        background = (238, 241, 232) if scene == "classic" else (255, 226, 173)
        stripe = (35, 71, 67) if scene == "classic" else (154, 61, 43)
        image = Image.new("RGB", (640, 480), color=background)
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((0, 0, 639, 84), fill=stripe)
        drawing.rectangle((52, 132, 588, 428), fill=(204, 220, 207))
        drawing.ellipse((250, 175, 390, 315), fill=(216, 157, 117))
        if overlay_enabled:
            drawing.text((24, 30), "SYNTHETIC CAMERA", fill=(255, 255, 255))

        output = BytesIO()
        try:
            image.save(output, format="JPEG", quality=quality)
        except (OSError, ValueError) as error:
            raise CameraOperationError("synthetic JPEG could not be rendered") from error
        return output.getvalue()