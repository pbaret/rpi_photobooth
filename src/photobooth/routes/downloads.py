"""Serve full-resolution photos through temporary download capabilities."""

from io import BytesIO
from typing import cast

from flask import Blueprint, abort, current_app, send_file
from flask.typing import ResponseReturnValue

from photobooth.services.downloads import DownloadError, DownloadService, DownloadTokenError
from photobooth.services.gallery import GalleryError

downloads_blueprint = Blueprint("downloads", __name__)


@downloads_blueprint.get("/download/<token>")
def download(token: str) -> ResponseReturnValue:
    """Return an authorized JPEG attachment without revealing storage paths."""
    service = cast(DownloadService, current_app.extensions["photobooth.downloads"])
    try:
        image_data = service.read_photo(token)
    except DownloadTokenError:
        abort(404)
    except (DownloadError, GalleryError):
        abort(503)
    return send_file(
        BytesIO(image_data),
        mimetype="image/jpeg",
        as_attachment=True,
        download_name="photobooth-photo.jpg",
    )