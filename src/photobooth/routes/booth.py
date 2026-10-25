"""HTTP routes for the touch-first booth experience and camera preview."""

from collections.abc import Iterator
from typing import cast

from flask import Blueprint, Response, current_app, render_template

from photobooth.camera.contract import CameraError
from photobooth.services.preview import PreviewService, PreviewSubscription

booth_blueprint = Blueprint("booth", __name__)


@booth_blueprint.get("/")
def index() -> str:
    """Render the booth screen; the embedded image opens preview on demand."""
    return render_template("booth/index.html")


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