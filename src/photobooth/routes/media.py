"""Serve managed originals and thumbnails through opaque photo identifiers."""

from typing import cast

from flask import Blueprint, Response, abort, current_app

from photobooth.services.gallery import (
	GalleryError,
	GalleryService,
	PhotoNotFoundError,
)

media_blueprint = Blueprint("media", __name__, url_prefix="/media")


@media_blueprint.get("/<photo_id>")
def photo(photo_id: str) -> Response:
	"""Return JPEG bytes only after GalleryService validates the photo ID."""
	gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
	try:
		image_data = gallery.read_photo(photo_id)
	except PhotoNotFoundError:
		abort(404)
	except GalleryError:
		abort(503)
	return Response(image_data, mimetype="image/jpeg")


@media_blueprint.get("/<photo_id>/thumbnail")
def thumbnail(photo_id: str) -> Response:
	"""Return a generated JPEG thumbnail for a currently managed photo."""
	gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
	try:
		image_data = gallery.read_thumbnail(photo_id)
	except PhotoNotFoundError:
		abort(404)
	except GalleryError:
		abort(503)
	return Response(image_data, mimetype="image/jpeg")