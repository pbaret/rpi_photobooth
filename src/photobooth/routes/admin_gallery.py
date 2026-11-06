"""Provide the authenticated administration view over managed gallery photos.

The blueprint shares the existing administration credential check. Listing
uses metadata and generated thumbnails only; deletion and full-resolution
reprints are delegated to GalleryService and PrintingService respectively.
"""

import re
import secrets
from typing import cast

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue

from photobooth.printing import PrintError
from photobooth.printing.service import PrintingService
from photobooth.routes.admin import require_admin_secret
from photobooth.services.gallery import (
    GalleryError,
    GalleryService,
    PhotoNotFoundError,
)

admin_gallery_blueprint = Blueprint(
    "admin_gallery", __name__, url_prefix="/admin/gallery"
)
admin_gallery_blueprint.before_request(require_admin_secret)

_PAGE_SIZE = 24
_PRINT_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{32}\Z")
_GALLERY_MESSAGES = {
    "deleted": "La photo a été supprimée.",
    "already-deleted": "Cette photo n'est plus disponible.",
    "delete-error": "La photo n'a pas pu être supprimée.",
    "submitted": (
        "Photo envoyée à l'imprimante. L'impression physique n'est pas confirmée."
    ),
    "placeholder": "Aucune impression physique n'est configurée sur cet appareil.",
    "duplicate": "Cette demande d'impression a déjà été reçue.",
    "unknown": (
        "L'envoi n'a pas pu être confirmé. Vérifiez la file d'impression avant "
        "de réessayer."
    ),
    "unavailable": "Imprimante indisponible.",
    "print-error": "L'impression n'a pas pu être effectuée.",
}


@admin_gallery_blueprint.get("")
def gallery() -> str | tuple[str, int]:
    """Render a newest-first page without reading original image contents.

    The page size is fixed at 24. GalleryService remains responsible for
    validating metadata and excluding unavailable items; only thumbnail URLs
    are placed in the rendered cards.
    """
    service = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    try:
        photos = list(reversed(service.list_photos()))
    except GalleryError:
        abort(503)

    page_count = (len(photos) + _PAGE_SIZE - 1) // _PAGE_SIZE
    page = _bounded_page(_requested_page(request.args.get("page")), page_count)
    start = (page - 1) * _PAGE_SIZE
    page_photos = photos[start : start + _PAGE_SIZE]
    return render_template(
        "admin/gallery.html",
        photos=page_photos,
        page=page,
        page_count=page_count,
        total_photos=len(photos),
        status=_GALLERY_MESSAGES.get(request.args.get("status", "")),
        print_keys={
            photo.photo_id: secrets.token_urlsafe(24) for photo in page_photos
        },
    )


@admin_gallery_blueprint.post("/<photo_id>/delete")
def delete_photo(photo_id: str) -> ResponseReturnValue:
    """Delete one managed photo and return to the nearest valid gallery page."""
    service = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    requested_page = _requested_page(request.form.get("page"))
    try:
        service.delete_photo(photo_id)
        status = "deleted"
    except PhotoNotFoundError:
        status = "already-deleted"
    except GalleryError:
        abort(503)

    try:
        remaining_count = len(service.list_photos())
    except GalleryError:
        abort(503)
    page_count = (remaining_count + _PAGE_SIZE - 1) // _PAGE_SIZE
    page = _bounded_page(requested_page, page_count)
    return redirect(
        url_for("admin_gallery.gallery", page=page, status=status), code=303
    )


@admin_gallery_blueprint.post("/<photo_id>/print")
def print_photo(photo_id: str) -> ResponseReturnValue:
    """Submit the managed original, deduplicating retries of this form only.

    A fresh random key is rendered for every visit to the gallery. The same
    POST body can therefore be safely retried, while a later explicit print
    action receives a different key and remains an intentional reprint.
    """
    request_key = request.form.get("idempotency_key", "")
    if _PRINT_KEY_PATTERN.fullmatch(request_key) is None:
        return _gallery_redirect("print-error")

    service = cast(GalleryService, current_app.extensions["photobooth.gallery"])
    printer = cast(PrintingService, current_app.extensions["photobooth.printer"])
    try:
        original = service.read_photo(photo_id)
    except PhotoNotFoundError:
        abort(404)
    except GalleryError:
        abort(503)

    try:
        result = printer.print_photo(original, f"admin:{photo_id}:{request_key}")
    except PrintError:
        return _gallery_redirect("print-error")
    return _gallery_redirect(result.status.value)


def _gallery_redirect(status: str) -> ResponseReturnValue:
    """Return print feedback through Post/Redirect/Get on the gallery."""
    return redirect(
        url_for(
            "admin_gallery.gallery",
            page=_requested_page(request.form.get("page")),
            status=status,
        ),
        code=303,
    )


def _requested_page(value: str | None) -> int:
    """Parse a bounded positive decimal page number, defaulting malformed input."""
    if value is None or re.fullmatch(r"[0-9]{1,9}", value) is None:
        return 1
    return max(1, int(value))


def _bounded_page(requested_page: int, page_count: int) -> int:
    """Clamp navigation to existing pages while keeping empty galleries on page one."""
    return min(requested_page, max(1, page_count))
