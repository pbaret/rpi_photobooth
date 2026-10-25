"""Behavioral tests for the initial Flask application."""

from typing import cast

from flask.testing import FlaskClient

from photobooth.app import create_app
from photobooth.camera.contract import CameraUnavailableError
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.services.preview import PreviewService


def test_booth_homepage_renders() -> None:
    """The application factory exposes a rendered booth page without hardware."""
    app = create_app()
    client: FlaskClient = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Photobooth" in response.data
    assert b"preview.mjpg" in response.data


def test_preview_endpoint_streams_synthetic_jpeg() -> None:
    """The HTTP preview emits multipart JPEG frames without physical hardware."""
    app = create_app(camera_backend=SyntheticCameraBackend())
    client: FlaskClient = app.test_client()
    response = client.get("/preview.mjpg", buffered=False)

    try:
        assert response.status_code == 200
        assert response.content_type == "multipart/x-mixed-replace; boundary=frame"
        first_part = cast(bytes, next(iter(response.response)))
        assert first_part.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n")
        assert b"\r\n\r\n\xff\xd8" in first_part
    finally:
        response.close()
        preview = cast(PreviewService, app.extensions["photobooth.preview"])
        preview.close()


def test_preview_endpoint_reports_unavailable_camera() -> None:
    """A camera acquisition failure is an HTTP error, not a broken stream."""

    class UnavailableCameraBackend(SyntheticCameraBackend):
        """Simulate an unavailable camera without opening physical hardware."""

        def start(self) -> None:
            """Fail acquisition using the public camera-domain exception."""
            raise CameraUnavailableError("synthetic camera unavailable")

    app = create_app(camera_backend=UnavailableCameraBackend())
    client: FlaskClient = app.test_client()

    response = client.get("/preview.mjpg")

    assert response.status_code == 503
    assert response.get_data(as_text=True) == "Camera preview is unavailable"