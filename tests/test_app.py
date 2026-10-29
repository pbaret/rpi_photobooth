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
from photobooth.services.gallery import GalleryService
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
    assert b"Ne bougez plus" in response.data
    assert b"capture/ready" in response.data
    assert b"error-panel" in response.data
    assert b'data-slideshow-enabled="true"' in response.data
    assert b"Touchez l'\xc3\xa9cran pour d\xc3\xa9marrer" in response.data


def test_slideshow_feed_returns_only_managed_thumbnail_urls(tmp_path: Path) -> None:
    """Slideshow media uses generated thumbnails and omits deleted photos."""
    app = create_app(
        configuration=_zero_countdown_configuration(tmp_path),
        camera_backend=SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()
    deleted_id = _capture_photo_id(client)
    retained_id = _capture_photo_id(client)
    assert client.post(f"/review/{deleted_id}/delete").status_code == 303

    response = client.get("/slideshow/photos.json")

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    typed_payload = cast(dict[str, object], payload)
    thumbnails = typed_payload.get("thumbnails")
    assert isinstance(thumbnails, list)
    thumbnails = cast(list[object], thumbnails)
    assert thumbnails == [f"/media/{retained_id}/thumbnail"]
    thumbnail_url = thumbnails[0]
    assert isinstance(thumbnail_url, str)
    assert client.get(thumbnail_url).mimetype == "image/jpeg"


def test_slideshow_feed_is_empty_without_photos_or_when_disabled(tmp_path: Path) -> None:
    """Empty galleries and disabled configuration produce no slideshow media."""
    configuration = _zero_countdown_configuration(tmp_path)
    client: FlaskClient = create_app(
        configuration=configuration,
        camera_backend=SyntheticCameraBackend(),
    ).test_client()

    assert client.get("/slideshow/photos.json").json == {"thumbnails": []}

    disabled = ApplicationConfig(
        startup=configuration.startup,
        booth=BoothSettings(countdown_seconds=0, slideshow_enabled=False),
        config_path=configuration.config_path,
    )
    disabled_client: FlaskClient = create_app(
        configuration=disabled,
        camera_backend=SyntheticCameraBackend(),
    ).test_client()
    assert b'data-slideshow-enabled="false"' in disabled_client.get("/").data
    assert disabled_client.get("/slideshow/photos.json").json == {"thumbnails": []}


def test_capture_endpoint_publishes_photo_and_opens_review(tmp_path: Path) -> None:
    """A successful capture persists its photo and redirects to review."""
    app = create_app(
        configuration=_zero_countdown_configuration(tmp_path),
        camera_backend=SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()

    response = client.post("/capture")

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    typed_payload = cast(dict[str, object], payload)
    review_path = typed_payload.get("review_url")
    assert isinstance(review_path, str)
    assert review_path.startswith("/review/")
    review_response = client.get(review_path)
    assert review_response.status_code == 200
    assert b"Nouvelle Photo" in review_response.data
    assert b"Supprimer" in review_response.data
    assert b"Imprimer" in review_response.data
    assert b'data-idle-timeout-seconds="120"' in review_response.data
    assert b'data-slideshow-enabled="true"' in review_response.data
    assert b"Touchez l'\xc3\xa9cran pour d\xc3\xa9marrer" in review_response.data
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    subscription = preview.subscribe()
    assert next(subscription).startswith(b"\xff\xd8")
    subscription.close()
    preview.close()


def test_capture_endpoint_hides_camera_failure_details(tmp_path: Path) -> None:
    """A recoverable camera failure returns a generic user-facing error."""

    class FailingCaptureBackend(SyntheticCameraBackend):
        """Raise a detailed backend error to verify route sanitization."""

        def capture(self, output_path: Path) -> None:
            """Fail capture with an implementation detail the route must hide."""
            raise CameraOperationError("private camera device detail")

    app = create_app(
        configuration=_zero_countdown_configuration(tmp_path),
        camera_backend=FailingCaptureBackend(),
    )
    client: FlaskClient = app.test_client()

    response = client.post("/capture")

    assert response.status_code == 503
    assert response.json == {"error": "capture_failed"}
    assert b"private camera device detail" not in response.data


@pytest.mark.parametrize("failure_mode", ["camera", "invalid_image"])
def test_capture_failure_can_be_retried(
    failure_mode: str, tmp_path: Path
) -> None:
    """Camera and image-validation failures leave later capture usable."""

    class FailOnceBackend(SyntheticCameraBackend):
        """Model a compliant backend that releases after its first failed still."""

        def __init__(self) -> None:
            """Fail the next capture once, then use the synthetic implementation."""
            super().__init__()
            self._failure_pending = True

        def capture(self, output_path: Path) -> None:
            """Emit one configured failure and stop, matching the backend contract."""
            if self._failure_pending:
                self._failure_pending = False
                self.stop()
                if failure_mode == "camera":
                    raise CameraOperationError("synthetic capture failure")
                output_path.write_bytes(b"not a JPEG")
                return
            super().capture(output_path)

    app = create_app(
        configuration=_zero_countdown_configuration(tmp_path),
        camera_backend=FailOnceBackend(),
    )
    client: FlaskClient = app.test_client()

    failed = client.post("/capture")
    recovered = client.post("/capture")

    assert failed.status_code == 503
    assert failed.json == {"error": "capture_failed"}
    assert recovered.status_code == 200
    payload = recovered.get_json()
    assert isinstance(payload, dict)
    typed_payload = cast(dict[str, object], payload)
    review_path = typed_payload.get("review_url")
    assert isinstance(review_path, str)
    assert client.get(review_path).status_code == 200
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    preview.close()


def test_browser_capture_waits_for_paint_acknowledgement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A synchronized capture cannot reach the camera before browser readiness."""
    countdown_complete = Event()
    still_started = Event()

    def finish_countdown(_: int) -> None:
        """Make the server countdown deterministic while exposing its completion."""
        countdown_complete.set()

    class ObservedCameraBackend(SyntheticCameraBackend):
        """Record when the still operation crosses into the camera backend."""

        def capture(self, output_path: Path) -> None:
            """Signal the still boundary before creating the synthetic photo."""
            still_started.set()
            super().capture(output_path)

    monkeypatch.setattr(preview_module, "sleep", finish_countdown)
    app = create_app(
        _zero_countdown_configuration(tmp_path), ObservedCameraBackend()
    )
    capture_statuses: list[int] = []

    def request_capture() -> None:
        """Run the blocking capture request on its own test-client thread."""
        response = app.test_client().post("/capture?wait_for_paint=true")
        capture_statuses.append(response.status_code)

    capture_thread = Thread(target=request_capture)
    capture_thread.start()
    try:
        assert countdown_complete.wait(timeout=1)
        assert not still_started.is_set()
        readiness = app.test_client().post("/capture/ready")
        assert readiness.status_code == 204
        capture_thread.join(timeout=2)
    finally:
        capture_thread.join(timeout=2)
        cast(PreviewService, app.extensions["photobooth.preview"]).close()

    assert not capture_thread.is_alive()
    assert capture_statuses == [200]
    assert still_started.is_set()


def test_capture_service_rejects_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second workflow is rejected while the first owns the reservation."""
    countdown_started = Event()
    finish_countdown = Event()

    def wait_for_countdown(_: int) -> None:
        countdown_started.set()
        if not finish_countdown.wait(timeout=2):
            raise TimeoutError("test countdown was not released")

    monkeypatch.setattr(preview_module, "sleep", wait_for_countdown)
    service = PreviewService(SyntheticCameraBackend(), GalleryService(tmp_path))
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


def _zero_countdown_configuration(data_root: Path = Path("data")) -> ApplicationConfig:
    """Use deterministic no-wait settings for capture route tests."""
    return ApplicationConfig(
        startup=StartupConfig(data_root=data_root),
        booth=BoothSettings(countdown_seconds=0),
        config_path=Path("test-config.json"),
    )


def _capture_photo_id(client: FlaskClient) -> str:
    """Capture through the HTTP workflow and return its opaque photo ID."""
    response = client.post("/capture")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    typed_payload = cast(dict[str, object], payload)
    review_path = typed_payload.get("review_url")
    assert isinstance(review_path, str)
    return review_path.rsplit("/", maxsplit=1)[-1]


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