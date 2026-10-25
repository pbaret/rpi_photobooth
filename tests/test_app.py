"""Behavioral tests for the initial Flask application."""

from pathlib import Path
from threading import Event, Thread
from typing import cast

import pytest
from flask.testing import FlaskClient

from photobooth.app import create_app
from photobooth.camera.contract import CameraOperationError, CameraUnavailableError
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import ApplicationConfig, BoothSettings, StartupConfig
from photobooth.services import preview as preview_module
from photobooth.services.preview import (
    CaptureInProgressError,
    PreviewService,
)


def test_booth_homepage_renders() -> None:
    """The application factory exposes a rendered booth page without hardware."""
    app = create_app()
    client: FlaskClient = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Photobooth" in response.data
    assert b"preview.mjpg" in response.data
    assert b"Prendre une photo" in response.data
    assert b"data-state=\"idle\"" in response.data
    assert b"countdown-panel" in response.data
    assert b"capturing-panel" in response.data
    assert b"error-panel" in response.data


def test_capture_endpoint_captures_and_releases_camera() -> None:
    """The booth can complete a real backend capture without storing a photo."""
    app = create_app(
        configuration=_zero_countdown_configuration(),
        camera_backend=SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()

    response = client.post("/capture")

    assert response.status_code == 200
    assert response.json == {"state": "idle"}
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    subscription = preview.subscribe()
    assert next(subscription).startswith(b"\xff\xd8")
    subscription.close()
    preview.close()


def test_capture_endpoint_hides_camera_failure_details() -> None:
    """A recoverable camera failure returns a generic user-facing error."""

    class FailingCaptureBackend(SyntheticCameraBackend):
        """Raise a detailed backend error to verify route sanitization."""

        def capture(self, output_path: Path) -> None:
            """Fail capture with an implementation detail the route must hide."""
            raise CameraOperationError("private camera device detail")

    app = create_app(
        configuration=_zero_countdown_configuration(),
        camera_backend=FailingCaptureBackend(),
    )
    client: FlaskClient = app.test_client()

    response = client.post("/capture")

    assert response.status_code == 503
    assert response.json == {"error": "capture_failed"}
    assert b"private camera device detail" not in response.data


def test_capture_service_rejects_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second workflow is rejected while the first owns the reservation."""
    countdown_started = Event()
    finish_countdown = Event()

    def wait_for_countdown(_: int) -> None:
        countdown_started.set()
        if not finish_countdown.wait(timeout=2):
            raise TimeoutError("test countdown was not released")

    monkeypatch.setattr(preview_module, "sleep", wait_for_countdown)
    service = PreviewService(SyntheticCameraBackend())
    subscription = service.subscribe()
    first_frame = next(subscription)
    assert first_frame.startswith(b"\xff\xd8")
    capture_errors: list[Exception] = []

    def first_capture() -> None:
        try:
            service.capture(3)
        except Exception as error:
            capture_errors.append(error)

    worker = Thread(target=first_capture)
    worker.start()
    try:
        assert countdown_started.wait(timeout=1)
        assert next(subscription).startswith(b"\xff\xd8")
        with pytest.raises(CaptureInProgressError):
            service.capture(0)
    finally:
        finish_countdown.set()
        worker.join(timeout=2)
        subscription.close()
        service.close()

    assert not worker.is_alive()
    assert capture_errors == []


def _zero_countdown_configuration() -> ApplicationConfig:
    """Use deterministic no-wait settings for capture route tests."""
    return ApplicationConfig(
        startup=StartupConfig(),
        booth=BoothSettings(countdown_seconds=0),
        config_path=Path("test-config.json"),
    )


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