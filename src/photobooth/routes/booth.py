"""HTTP routes for the touch-first booth experience and camera preview."""

from collections.abc import Iterator
from typing import cast

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
import base64

from photobooth.camera.contract import CameraError
from photobooth.config import ApplicationConfig, ConfigurationError, validate_public_base_url
from photobooth.printing import PrintError, PrinterBackend
from photobooth.services.gallery import (
    GalleryError,
    GalleryService,
    PhotoNotFoundError,
)
from photobooth.services.downloads import DownloadError, DownloadService
from photobooth.services.backgrounds import BackgroundService
from photobooth.services.preview import (
    CaptureInProgressError,
    CaptureReadyTimeoutError,
    PreviewService,
    PreviewSubscription,
)
from photobooth.theme import ThemeSettings

booth_blueprint = Blueprint("booth", __name__)


@booth_blueprint.context_processor
def participant_theme() -> dict[str, object]:
    """Expose the current event theme to every participant template.

    ``theme_variables`` contains only validated CSS custom properties. The
    background URL is supplied only while the managed image still exists, so
    a removed image falls back to the configured background color.
    """
    theme = cast(ThemeSettings, current_app.extensions["photobooth.theme"])
    backgrounds = cast(
        BackgroundService, current_app.extensions["photobooth.backgrounds"]
    )
    image = theme.background.image
    background_url = (
        url_for("media.background", background_id=image)
        if image is not None and backgrounds.exists(image)
        else None
    )
    return {
        "theme": theme,
        "theme_variables": theme.css_variables(),
        "background_url": background_url,
    }


@booth_blueprint.get("/")
def index() -> str:
    """Render the booth screen; the embedded image opens preview on demand."""
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    return render_template(
        "booth/index.html",
        countdown_seconds=configuration.booth.countdown_seconds,
        idle_timeout_seconds=configuration.booth.idle_timeout_seconds,
        slideshow_enabled=configuration.booth.slideshow_enabled,
        slideshow_interval_seconds=configuration.booth.slideshow_interval_seconds,
        booth_name=configuration.booth.booth_name,
        notice=_booth_notice(),
    )


@booth_blueprint.get("/slideshow/photos.json")
def slideshow_photos() -> ResponseReturnValue:
    """Return currently managed slideshow thumbnails in capture order."""
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    if not configuration.booth.slideshow_enabled:
        return jsonify(thumbnails=[])

    gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    try:
        photos = gallery.list_photos()
    except GalleryError:
        abort(503)
    return jsonify(
        thumbnails=[
            url_for("media.thumbnail", photo_id=photo.photo_id) for photo in photos
        ]
    )


@booth_blueprint.post("/capture")
def capture() -> ResponseReturnValue:
    """Capture a photo and return its review URL to the booth client."""
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    service = cast(PreviewService, current_app.extensions["photobooth.preview"])
    try:
        photo = service.capture(
            configuration.booth.countdown_seconds,
            wait_for_ready=request.args.get("wait_for_paint") == "true",
        )
    except CaptureInProgressError:
        return jsonify(error="capture_in_progress"), 409
    except (CameraError, GalleryError, CaptureReadyTimeoutError):
        return jsonify(error="capture_failed"), 503
    return jsonify(review_url=url_for("booth.review", photo_id=photo.photo_id))


@booth_blueprint.post("/capture/ready")
def capture_ready() -> ResponseReturnValue:
    """Acknowledge that the browser has painted the supplemental-light screen."""
    service = cast(PreviewService, current_app.extensions["photobooth.preview"])
    if not service.signal_capture_ready():
        return jsonify(error="capture_not_waiting"), 409
    return Response(status=204)


@booth_blueprint.get("/review/<photo_id>")
def review(photo_id: str) -> str:
    """Render the captured photo and touch actions after managed lookup."""
    gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    try:
        photo = gallery.get_photo(photo_id)
    except PhotoNotFoundError:
        abort(404)
    except GalleryError:
        abort(503)
    print_status = request.args.get("print_status")
    if print_status not in {"placeholder", "submitted", "error"}:
        print_status = None
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    downloads = cast(DownloadService, current_app.extensions["photobooth.downloads"])
    qr_data_uri: str | None = None
    download_error: str | None = None
    try:
        public_base_url = validate_public_base_url(
            configuration.startup.public_base_url
        )
        token = downloads.create_token(photo_id)
        download_url = downloads.build_download_url(token.token, public_base_url)
        qr_png = downloads.create_qr_png(download_url)
        qr_data_uri = "data:image/png;base64," + base64.b64encode(qr_png).decode("ascii")
    except ConfigurationError as error:
        download_error = str(error)
    except (DownloadError, GalleryError):
        abort(503)
    return render_template(
        "booth/review.html",
        photo=photo,
        photo_url=url_for("media.photo", photo_id=photo_id),
        photo_aspect=f"{photo.width / photo.height:.4f}",
        qr_data_uri=qr_data_uri,
        download_error=download_error,
        print_status=print_status,
        idle_timeout_seconds=configuration.booth.idle_timeout_seconds,
        slideshow_enabled=configuration.booth.slideshow_enabled,
        slideshow_interval_seconds=configuration.booth.slideshow_interval_seconds,
        wifi_network_name=configuration.booth.wifi_network_name,
    )


@booth_blueprint.post("/review/<photo_id>/retake")
def retake(photo_id: str) -> ResponseReturnValue:
    """Return to ready mode without deleting the photo or starting a countdown."""
    gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    try:
        gallery.get_photo(photo_id)
    except PhotoNotFoundError:
        abort(404)
    except GalleryError:
        abort(503)
    return redirect(url_for("booth.index"), code=303)


@booth_blueprint.post("/review/<photo_id>/delete")
def delete_photo(photo_id: str) -> ResponseReturnValue:
    """Invalidate the managed photo, then return to the ready booth."""
    gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    try:
        gallery.delete_photo(photo_id)
    except PhotoNotFoundError:
        return redirect(url_for("booth.index", notice="already-deleted"), code=303)
    except GalleryError:
        abort(503)
    return redirect(url_for("booth.index", notice="deleted"), code=303)


@booth_blueprint.post("/review/<photo_id>/print")
def print_photo(photo_id: str) -> ResponseReturnValue:
    """Send one managed photo to the configured printer abstraction."""
    gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    printer = cast(PrinterBackend, current_app.extensions["photobooth.printer"])
    try:
        print_status = printer.print_photo(gallery.read_photo(photo_id))
    except PhotoNotFoundError:
        abort(404)
    except (GalleryError, PrintError):
        return redirect(
            url_for("booth.review", photo_id=photo_id, print_status="error"),
            code=303,
        )
    return redirect(
        url_for(
            "booth.review", photo_id=photo_id, print_status=print_status.value
        ),
        code=303,
    )


@booth_blueprint.get("/preview.mjpg")
def preview() -> Response:
    """Stream shared JPEG frames or report camera startup failure as HTTP 503."""
    service = cast(PreviewService, current_app.extensions["photobooth.preview"])
    try:
        subscription = service.subscribe()
    except CameraError:
        return Response("Camera preview is unavailable", status=503, mimetype="text/plain")

    response = Response(
        _multipart_frames(subscription),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )
    response.call_on_close(subscription.close)
    return response


def _multipart_frames(subscription: PreviewSubscription) -> Iterator[bytes]:
    """Encode each shared JPEG as one standards-shaped MJPEG part."""
    try:
        for image in subscription:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(image)}\r\n\r\n".encode("ascii")
                + image
                + b"\r\n"
            )
    finally:
        subscription.close()


def _booth_notice() -> str | None:
    """Map known navigation outcomes to fixed text without reflecting input."""
    notice = request.args.get("notice")
    notices = {
        "deleted": "La photo a été supprimée.",
        "already-deleted": "Cette photo avait déjà été supprimée.",
    }
    return notices.get(notice) if notice is not None else None