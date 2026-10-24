"""Provide a deterministic, hardware-free implementation of CameraBackend.

The backend is intended for automated tests and development of application
workflows that need camera-shaped JPEG data without acquiring a device.
"""

from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image, ImageDraw

from photobooth.camera.contract import CameraOperationError, CameraUnavailableError


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

    def start(self) -> None:
        """Make preview available; repeated calls leave the backend started."""
        with self._lock:
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
                return self._render_jpeg()
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
                output_path.write_bytes(self._render_jpeg())
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

    @staticmethod
    def _render_jpeg() -> bytes:
        """Render a fixed synthetic test scene as a JPEG image."""
        image = Image.new("RGB", (640, 480), color=(238, 241, 232))
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((0, 0, 639, 84), fill=(35, 71, 67))
        drawing.rectangle((52, 132, 588, 428), fill=(204, 220, 207))
        drawing.ellipse((250, 175, 390, 315), fill=(216, 157, 117))
        drawing.text((24, 30), "SYNTHETIC CAMERA", fill=(255, 255, 255))

        output = BytesIO()
        try:
            image.save(output, format="JPEG", quality=85)
        except (OSError, ValueError) as error:
            raise CameraOperationError("synthetic JPEG could not be rendered") from error
        return output.getvalue()