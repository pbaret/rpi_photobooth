"""Verify authenticated administration-gallery listing and actions."""

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import cast
from urllib.parse import parse_qs, urlsplit

from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
import pytest

from photobooth.app import create_app
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import ApplicationConfig, BoothSettings, StartupConfig
from photobooth.printing.contract import PrintError, PrintResult, PrintStatus
from photobooth.printing.settings import PrinterBackendKind, PrintingSettings
from photobooth.services.downloads import DownloadService, DownloadTokenNotFoundError
from photobooth.services.gallery import (
    GalleryMetadataError,
    GalleryService,
    PhotoMetadata,
)

_ADMIN_SECRET = "gallery-test-secret"


class RecordingPrinter:
    """Keep submitted original JPEG bytes for behavior assertions."""

    def __init__(self) -> None:
        """Start with no submitted jobs."""
        self.images: list[bytes] = []

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Record a backend submission and return a stable accepted-job result."""
        del idempotency_key
        self.images.append(image_data)
        return PrintResult(
            status=PrintStatus.SUBMITTED,
            queue_name="test-queue",
            job_id=f"test-queue-{len(self.images)}",
            status_text="submitted",
        )


class FailingPrinter:
    """Raise a controlled print error to verify safe administrator feedback."""

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Fail without returning low-level process output to the route."""
        del image_data, idempotency_key
        raise PrintError("unbounded private subprocess output")


def _app(
    tmp_path: Path,
    printer_backend: RecordingPrinter | FailingPrinter | None = None,
    printing: PrintingSettings | None = None,
) -> Flask:
    """Create an isolated app with local storage and an authenticated admin."""
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret=_ADMIN_SECRET,
        ),
        booth=BoothSettings(),
        config_path=tmp_path / "config.json",
        printing=printing if printing is not None else PrintingSettings(),
    )
    return create_app(
        configuration=configuration,
        camera_backend=SyntheticCameraBackend(),
        printer_backend=printer_backend,
    )


def _auth_headers() -> dict[str, str]:
    """Build the existing HTTP Basic credential for the test administrator."""
    encoded = base64.b64encode(f"admin:{_ADMIN_SECRET}".encode()).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _add_photo(
    gallery: GalleryService,
    tmp_path: Path,
    index: int,
    captured_at: datetime | None = None,
) -> PhotoMetadata:
    """Publish a small deterministic JPEG and optionally set its stored time."""
    source = tmp_path / f"source-{index}.jpg"
    Image.new("RGB", (40 + index, 30), (index % 255, 90, 150)).save(
        source, format="JPEG"
    )
    photo = gallery.register_captured_photo(source)
    if captured_at is None:
        return photo

    metadata_path = tmp_path / "data" / "metadata" / f"{photo.photo_id}.json"
    document = json.loads(metadata_path.read_text(encoding="utf-8"))
    document["captured_at"] = captured_at.isoformat()
    metadata_path.write_text(json.dumps(document), encoding="utf-8")
    return PhotoMetadata(photo.photo_id, captured_at, photo.width, photo.height)


def _gallery_from(app: Flask) -> GalleryService:
    """Return the app-owned gallery service for test fixture setup."""
    return cast(GalleryService, app.extensions["photobooth.gallery"])


def test_admin_gallery_and_mutations_require_admin_authentication(
    tmp_path: Path,
) -> None:
    """The listing and both actions share the existing admin auth boundary."""
    app = _app(tmp_path)
    gallery = _gallery_from(app)
    photo = _add_photo(gallery, tmp_path, 1)
    client: FlaskClient = app.test_client()

    assert client.get("/admin/gallery").status_code == 401
    assert client.post(f"/admin/gallery/{photo.photo_id}/delete").status_code == 401
    assert client.post(f"/admin/gallery/{photo.photo_id}/print").status_code == 401

    page = client.get("/admin/gallery", headers=_auth_headers())
    admin = client.get("/admin", headers=_auth_headers())
    assert page.status_code == 200
    assert b"Galerie" in page.data
    assert b"Gallery" in admin.data
    assert b"/review/" not in admin.data


def test_gallery_empty_and_lists_only_valid_newest_thumbnails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad entries do not hide valid photos, and listing never reads originals."""
    app = _app(tmp_path)
    gallery = _gallery_from(app)
    client: FlaskClient = app.test_client()

    empty = client.get("/admin/gallery", headers=_auth_headers())
    assert b"Aucune photo dans la galerie." in empty.data

    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    oldest = _add_photo(gallery, tmp_path, 1, now)
    missing_thumbnail = _add_photo(gallery, tmp_path, 2, now + timedelta(minutes=1))
    newest = _add_photo(gallery, tmp_path, 3, now + timedelta(minutes=2))
    malformed = _add_photo(gallery, tmp_path, 4, now + timedelta(minutes=3))
    (tmp_path / "data" / "thumbnails" / f"{missing_thumbnail.photo_id}.jpg").unlink()
    malformed_path = tmp_path / "data" / "metadata" / f"{malformed.photo_id}.json"
    malformed_path.write_text("{broken", encoding="utf-8")

    def reject_original_read(self: GalleryService, photo_id: str) -> bytes:
        """Fail if listing accidentally loads an original JPEG."""
        del self, photo_id
        raise AssertionError("gallery listing read an original photo")

    monkeypatch.setattr(GalleryService, "read_photo", reject_original_read)
    response = client.get("/admin/gallery", headers=_auth_headers())

    assert response.status_code == 200
    assert response.data.index(newest.photo_id.encode()) < response.data.index(
        oldest.photo_id.encode()
    )
    assert f"/media/{newest.photo_id}/thumbnail".encode() in response.data
    assert f"/media/{oldest.photo_id}/thumbnail".encode() in response.data
    assert f"/media/{newest.photo_id}\"".encode() not in response.data
    assert missing_thumbnail.photo_id.encode() not in response.data
    assert malformed.photo_id.encode() not in response.data
    with pytest.raises(GalleryMetadataError):
        gallery.get_photo(malformed.photo_id)


def test_gallery_paginates_and_normalizes_invalid_page_numbers(tmp_path: Path) -> None:
    """Pages contain at most 24 newest items and expose adjacent navigation."""
    app = _app(tmp_path)
    gallery = _gallery_from(app)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    photos = [
        _add_photo(gallery, tmp_path, index, now + timedelta(minutes=index))
        for index in range(25)
    ]
    client: FlaskClient = app.test_client()
    headers = _auth_headers()

    first = client.get("/admin/gallery", headers=headers)
    assert first.data.count(b'class="photo-card"') == 24
    assert photos[-1].photo_id.encode() in first.data
    assert photos[0].photo_id.encode() not in first.data
    assert b'rel="next"' in first.data

    second = client.get("/admin/gallery?page=2", headers=headers)
    assert second.data.count(b'class="photo-card"') == 1
    assert photos[0].photo_id.encode() in second.data
    assert b'rel="prev"' in second.data
    assert b"Page 2 sur 2" in second.data

    invalid = client.get("/admin/gallery?page=abc", headers=headers)
    beyond = client.get("/admin/gallery?page=999", headers=headers)
    assert b"Page 1 sur 2" in invalid.data
    assert b"Page 2 sur 2" in beyond.data


def test_deleting_last_page_item_clamps_page_and_invalidates_media_and_token(
    tmp_path: Path,
) -> None:
    """Deletion delegates cleanup and keeps navigation on the nearest page."""
    app = _app(tmp_path)
    gallery = _gallery_from(app)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    photos = [
        _add_photo(gallery, tmp_path, index, now + timedelta(minutes=index))
        for index in range(25)
    ]
    downloads = cast(DownloadService, app.extensions["photobooth.downloads"])
    token = downloads.create_token(photos[0].photo_id)
    client: FlaskClient = app.test_client()

    response = client.post(
        f"/admin/gallery/{photos[0].photo_id}/delete",
        data={"page": "2"},
        headers=_auth_headers(),
    )

    assert response.status_code == 303
    assert parse_qs(urlsplit(response.headers["Location"]).query) == {
        "page": ["1"],
        "status": ["deleted"],
    }
    assert client.get(f"/media/{photos[0].photo_id}").status_code == 404
    assert client.get(f"/media/{photos[0].photo_id}/thumbnail").status_code == 404
    deleted_print = client.post(
        f"/admin/gallery/{photos[0].photo_id}/print",
        data={"idempotency_key": "A" * 32},
        headers=_auth_headers(),
    )
    assert deleted_print.status_code == 404
    with pytest.raises(DownloadTokenNotFoundError):
        downloads.read_photo(token.token)


def test_gallery_print_retries_are_deduplicated_but_explicit_reprints_work(
    tmp_path: Path,
) -> None:
    """A form key blocks duplicate delivery without blocking a later reprint."""
    printer = RecordingPrinter()
    app = _app(
        tmp_path,
        printer,
        PrintingSettings(backend=PrinterBackendKind.CUPS, queue_name="test-queue"),
    )
    gallery = _gallery_from(app)
    photo = _add_photo(gallery, tmp_path, 1)
    original = gallery.read_photo(photo.photo_id)
    client: FlaskClient = app.test_client()
    headers = _auth_headers()

    def print_key() -> str:
        """Read the fresh hidden idempotency key rendered for this card."""
        page = client.get("/admin/gallery", headers=headers)
        match = re.search(
            rb'name="idempotency_key" value="([A-Za-z0-9_-]{32})"', page.data
        )
        assert match is not None
        return match.group(1).decode("ascii")

    first_key = print_key()
    first = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"page": "1", "idempotency_key": first_key},
        headers=headers,
    )
    retry = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"page": "1", "idempotency_key": first_key},
        headers=headers,
    )
    assert first.status_code == retry.status_code == 303
    assert "status=submitted" in first.headers["Location"]
    assert "status=duplicate" in retry.headers["Location"]
    assert printer.images == [original]

    second_key = print_key()
    assert second_key != first_key
    second = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"page": "1", "idempotency_key": second_key},
        headers=headers,
    )
    assert "status=submitted" in second.headers["Location"]
    assert printer.images == [original, original]


def test_gallery_print_uses_null_backend_and_rejects_bad_requests(
    tmp_path: Path,
) -> None:
    """The development null backend stays a placeholder and invalid IDs are safe."""
    app = _app(tmp_path)
    gallery = _gallery_from(app)
    photo = _add_photo(gallery, tmp_path, 1)
    client: FlaskClient = app.test_client()
    response = client.get("/admin/gallery", headers=_auth_headers())
    match = re.search(
        rb'name="idempotency_key" value="([A-Za-z0-9_-]{32})"', response.data
    )
    assert match is not None

    placeholder = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"idempotency_key": match.group(1).decode("ascii")},
        headers=_auth_headers(),
    )
    invalid_key = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"idempotency_key": "invalid"},
        headers=_auth_headers(),
    )
    unknown = client.post(
        f"/admin/gallery/{'A' * 24}/print",
        data={"idempotency_key": match.group(1).decode("ascii")},
        headers=_auth_headers(),
    )
    assert "status=placeholder" in placeholder.headers["Location"]
    assert "status=print-error" in invalid_key.headers["Location"]
    assert unknown.status_code == 404


def test_print_failure_is_generic_and_leaves_gallery_available(
    tmp_path: Path,
) -> None:
    """A printer error is not exposed and does not make the gallery unusable."""
    app = _app(
        tmp_path,
        FailingPrinter(),
        PrintingSettings(backend=PrinterBackendKind.CUPS, queue_name="test-queue"),
    )
    photo = _add_photo(_gallery_from(app), tmp_path, 1)
    client: FlaskClient = app.test_client()
    page = client.get("/admin/gallery", headers=_auth_headers())
    match = re.search(
        rb'name="idempotency_key" value="([A-Za-z0-9_-]{32})"', page.data
    )
    assert match is not None

    response = client.post(
        f"/admin/gallery/{photo.photo_id}/print",
        data={"idempotency_key": match.group(1).decode("ascii")},
        headers=_auth_headers(),
    )
    feedback = client.get(response.headers["Location"], headers=_auth_headers())

    assert response.status_code == 303
    assert b"n&#39;a pas pu" in feedback.data
    assert b"unbounded private subprocess output" not in feedback.data
    assert feedback.status_code == 200


def test_delete_unknown_photo_keeps_gallery_usable(tmp_path: Path) -> None:
    """Repeated or unknown delete actions return safely to the gallery."""
    app = _app(tmp_path)
    client: FlaskClient = app.test_client()

    response = client.post(
        f"/admin/gallery/{'A' * 24}/delete",
        data={"page": "1"},
        headers=_auth_headers(),
    )

    assert response.status_code == 303
    assert "status=already-deleted" in response.headers["Location"]
    assert client.get(response.headers["Location"], headers=_auth_headers()).status_code == 200
