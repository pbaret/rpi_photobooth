"""HTTP routes for the touch-first booth experience and camera preview."""

from collections.abc import Iterator
from typing import cast

from flask import Blueprint, Response, current_app, jsonify, render_template

from photobooth.camera.contract import CameraError
from photobooth.config import ApplicationConfig
from photobooth.services.preview import (
    CaptureInProgressError,
    PreviewService,
    PreviewSubscription,
)

booth_blueprint = Blueprint("booth", __name__)


@booth_blueprint.get("/")
def index() -> str:
    """Render the booth screen; the embedded image opens preview on demand."""
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    return render_template(
        "booth/index.html",
        countdown_seconds=configuration.booth.countdown_seconds,
        booth_name=configuration.booth.booth_name,
    )


@booth_blueprint.post("/capture")
def capture() -> Response | tuple[Response, int]:
    """Run one serialized capture workflow without exposing camera details."""
    configuration = cast(
        ApplicationConfig, current_app.extensions["photobooth.configuration"]
    )
    service = cast(PreviewService, current_app.extensions["photobooth.preview"])
    try:
        service.capture(configuration.booth.countdown_seconds)
    except CaptureInProgressError:
        return jsonify(error="capture_in_progress"), 409
    except CameraError:
        return jsonify(error="capture_failed"), 503
    return jsonify(state="idle")


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