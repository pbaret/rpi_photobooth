"""Verify persistent gallery behavior and review actions without hardware."""

from io import BytesIO
import json
from pathlib import Path
from typing import cast

from flask.testing import FlaskClient
from PIL import Image
import pytest

from photobooth.app import create_app
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import ApplicationConfig, BoothSettings, StartupConfig
from photobooth.printing.contract import PrintStatus
from photobooth.services.gallery import (
    GalleryMetadataError,
    GalleryService,
    InvalidPhotoError,
    PhotoNotFoundError,
)


def test_registration_persists_metadata_and_creates_readable_thumbnail(
    tmp_path: Path,
) -> None:
    """Published photos survive service recreation and have a bounded thumbnail."""
    source_path = tmp_path / "capture.jpg"
    Image.new("RGB", (800, 600), color=(30, 120, 210)).save(source_path, format="JPEG")
    gallery = GalleryService(tmp_path / "data")

    photo = gallery.register_captured_photo(source_path)
    reloaded = GalleryService(tmp_path / "data")
    resolved = reloaded.get_photo(photo.photo_id)
    thumbnail_bytes = reloaded.read_thumbnail(photo.photo_id)

    assert resolved == photo
    assert reloaded.read_photo(photo.photo_id).startswith(b"\xff\xd8")
    with Image.open(BytesIO(thumbnail_bytes)) as thumbnail:
        assert thumbnail.size == (480, 360)
        assert thumbnail.format == "JPEG"
    record = json.loads(
        (tmp_path / "data" / "metadata" / f"{photo.photo_id}.json").read_text()
    )
    assert record["photo_id"] == photo.photo_id
    assert record["width"] == 800
    assert record["height"] == 600


def test_corrupt_capture_is_rejected_without_publication(tmp_path: Path) -> None:
    """A corrupt source cannot become a managed photo or leave artifacts."""
    source_path = tmp_path / "capture.jpg"
    source_path.write_bytes(b"not a JPEG")
    gallery = GalleryService(tmp_path / "data")

    with pytest.raises(InvalidPhotoError):
        gallery.register_captured_photo(source_path)

    assert not list((tmp_path / "data").rglob("*.jpg"))
    assert not list((tmp_path / "data").rglob("*.json"))


def test_malformed_metadata_is_reported_as_controlled_gallery_error(
    tmp_path: Path,
) -> None:
    """Malformed persisted JSON does not masquerade as an unknown photo."""
    gallery = GalleryService(tmp_path / "data")
    metadata_directory = tmp_path / "data" / "metadata"
    metadata_directory.mkdir(parents=True)
    (metadata_directory / ("A" * 24 + ".json")).write_text("{broken", encoding="utf-8")

    with pytest.raises(GalleryMetadataError):
        gallery.get_photo("A" * 24)


def test_unknown_and_path_traversal_ids_are_not_resolved(tmp_path: Path) -> None:
    """Invalid identifiers never derive a path outside managed storage."""
    gallery = GalleryService(tmp_path / "data")

    for photo_id in ("unknown-photo-id-123456", "../" + "A" * 24, "..\\" + "A" * 24):
        with pytest.raises(PhotoNotFoundError):
            gallery.get_photo(photo_id)

    assert list(tmp_path.iterdir()) == []


def test_delete_invalidates_media_and_cleans_thumbnail(tmp_path: Path) -> None:
    """Deleting a photo removes its metadata, original, and thumbnail."""
    source_path = tmp_path / "capture.jpg"
    Image.new("RGB", (64, 48), color=(180, 80, 30)).save(source_path, format="JPEG")
    gallery = GalleryService(tmp_path / "data")
    photo = gallery.register_captured_photo(source_path)
    thumbnail_path = tmp_path / "data" / "thumbnails" / f"{photo.photo_id}.jpg"

    gallery.delete_photo(photo.photo_id)

    assert not thumbnail_path.exists()
    with pytest.raises(PhotoNotFoundError):
        gallery.read_photo(photo.photo_id)
    with pytest.raises(PhotoNotFoundError):
        gallery.delete_photo(photo.photo_id)


def test_list_photos_returns_thumbnail_eligible_photos_in_capture_order(
    tmp_path: Path,
) -> None:
    """The slideshow list excludes deleted items and has deterministic ordering."""
    source_path = tmp_path / "capture.jpg"
    Image.new("RGB", (64, 48), color=(180, 80, 30)).save(source_path, format="JPEG")
    gallery = GalleryService(tmp_path / "data")
    first = gallery.register_captured_photo(source_path)
    second = gallery.register_captured_photo(source_path)

    listed = gallery.list_photos()

    assert listed == sorted(
        [first, second], key=lambda photo: (photo.captured_at, photo.photo_id)
    )
    gallery.delete_photo(first.photo_id)

    listed = gallery.list_photos()

    assert listed == [second]


def test_capture_review_print_retake_and_delete_routes(tmp_path: Path) -> None:
    """Review actions use POST and preserve or invalidate managed media correctly."""

    class RecordingPrinter:
        """Record one image submission through the printer abstraction."""

        def __init__(self) -> None:
            self.images: list[bytes] = []

        def print_photo(self, image_data: bytes) -> PrintStatus:
            """Retain submitted bytes for assertions, without hardware."""
            self.images.append(image_data)
            return PrintStatus.SUBMITTED

    printer = RecordingPrinter()
    configuration = ApplicationConfig(
        startup=StartupConfig(data_root=tmp_path / "data"),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
    )
    app = create_app(configuration, SyntheticCameraBackend(), printer_backend=printer)
    client: FlaskClient = app.test_client()

    review_path = _capture_review_path(client)
    photo_id = review_path.rsplit("/", maxsplit=1)[-1]
    assert review_path.startswith("/review/")
    assert client.get(review_path).status_code == 200
    media_response = client.get(f"/media/{photo_id}")
    assert media_response.status_code == 200
    assert media_response.mimetype == "image/jpeg"

    printed = client.post(f"/review/{photo_id}/print")
    assert printed.status_code == 303
    assert f"/review/{photo_id}?print_status=submitted" in printed.headers["Location"]
    assert b"Demande d'impression envoy\xc3\xa9e" in client.get(printed.headers["Location"]).data
    assert len(printer.images) == 1

    retaken = client.post(f"/review/{photo_id}/retake")
    assert retaken.status_code == 303
    assert retaken.headers["Location"] == "/"
    booth_response = client.get(retaken.headers["Location"])
    assert b'data-state="idle"' in booth_response.data
    assert client.get(f"/media/{photo_id}").status_code == 200
    preview_response = client.get("/preview.mjpg", buffered=False)
    assert preview_response.status_code == 200
    preview_response.close()

    second_photo_id = _capture_review_path(client).rsplit("/", 1)[-1]
    deleted = client.post(f"/review/{second_photo_id}/delete")
    assert deleted.status_code == 303
    assert deleted.headers["Location"] == "/?notice=deleted"
    assert client.get(f"/media/{second_photo_id}").status_code == 404
    repeated = client.post(f"/review/{second_photo_id}/delete")
    assert repeated.status_code == 303
    assert repeated.headers["Location"] == "/?notice=already-deleted"


def test_review_and_media_unknown_ids_return_not_found(tmp_path: Path) -> None:
    """Review and image routes expose unknown IDs as ordinary HTTP 404 responses."""
    app = create_app(
        ApplicationConfig(
            startup=StartupConfig(data_root=tmp_path / "data"),
            booth=BoothSettings(countdown_seconds=0),
            config_path=tmp_path / "config.json",
        ),
        SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()

    assert client.get("/review/" + "A" * 24).status_code == 404
    assert client.get("/media/" + "A" * 24).status_code == 404
    assert client.post("/review/" + "A" * 24 + "/retake").status_code == 404


def test_null_printer_reports_placeholder_without_leaving_review(tmp_path: Path) -> None:
    """The default development printer returns a visible placeholder status."""
    app = create_app(
        ApplicationConfig(
            startup=StartupConfig(data_root=tmp_path / "data"),
            booth=BoothSettings(countdown_seconds=0),
            config_path=tmp_path / "config.json",
        ),
        SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()
    review_path = _capture_review_path(client)
    photo_id = review_path.rsplit("/", maxsplit=1)[-1]

    printed = client.post(f"/review/{photo_id}/print")

    assert printed.status_code == 303
    assert f"/review/{photo_id}?print_status=placeholder" in printed.headers["Location"]
    assert b"Impression non configur\xc3\xa9e" in client.get(printed.headers["Location"]).data


def _capture_review_path(client: FlaskClient) -> str:
    """Capture one synthetic photo and return its validated review URL."""
    response = client.post("/capture")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    typed_payload = cast(dict[str, object], payload)
    review_path = typed_payload.get("review_url")
    assert isinstance(review_path, str)
    return review_path