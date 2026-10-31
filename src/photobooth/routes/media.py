"""Serve managed originals, thumbnails and event backgrounds by opaque identifier."""

from typing import cast

from flask import Blueprint, Response, abort, current_app

from photobooth.services.backgrounds import (
	BackgroundError,
	BackgroundNotFoundError,
	BackgroundService,
)
from photobooth.services.gallery import (
	GalleryError,
	GalleryService,
	PhotoNotFoundError,
)

media_blueprint = Blueprint("media", __name__, url_prefix="/media")

# Background identifiers are immutable, so browsers may reuse them across pages.
_BACKGROUND_CACHE_SECONDS = 86400


@media_blueprint.get("/backgrounds/<background_id>")
def background(background_id: str) -> Response:
	"""Return a stored event background after BackgroundService validates its ID."""
	backgrounds = cast(BackgroundService, current_app.extensions["photobooth.backgrounds"])
	try:
		content = backgrounds.read(background_id)
	except BackgroundNotFoundError:
		abort(404)
	except BackgroundError:
		abort(503)
	response = Response(content.data, mimetype=content.mimetype)
	response.cache_control.public = True
	response.cache_control.max_age = _BACKGROUND_CACHE_SECONDS
	return response


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