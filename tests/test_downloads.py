"""Verify persisted download tokens and QR-based photo downloads."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable
from typing import cast

from flask.testing import FlaskClient
from PIL import Image
import pytest

from photobooth.app import create_app
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import ApplicationConfig, BoothSettings, StartupConfig
from photobooth.services.downloads import (
    DownloadService,
    DownloadTokenExpiredError,
    DownloadTokenNotFoundError,
    DownloadTokenRevokedError,
)
from photobooth.services.gallery import GalleryService


def _services(
    tmp_path: Path,
    clock: Callable[[], datetime] | None = None,
) -> tuple[GalleryService, str, DownloadService]:
    """Create a managed test image and a token service in isolated storage."""
    source_path = tmp_path / "source.jpg"
    Image.new("RGB", (64, 48), color=(30, 120, 210)).save(source_path, format="JPEG")
    gallery = GalleryService(tmp_path / "data")
    photo = gallery.register_captured_photo(source_path)
    if clock is None:
        downloads = DownloadService(tmp_path / "data", gallery, 3600)
    else:
        downloads = DownloadService(tmp_path / "data", gallery, 3600, clock)
    return gallery, photo.photo_id, downloads


def test_token_persists_maps_to_photo_and_builds_lan_qr_url(tmp_path: Path) -> None:
    """A persisted random token resolves its one photo and produces a QR PNG."""
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    gallery, photo_id, downloads = _services(tmp_path, lambda: now)

    token = downloads.create_token(photo_id)
    reloaded = DownloadService(tmp_path / "data", gallery, 3600, lambda: now)
    url = reloaded.build_download_url(token.token, "http://192.168.1.42:5000")

    assert token.token != photo_id
    assert url == f"http://192.168.1.42:5000/download/{token.token}"
    assert reloaded.read_photo(token.token).startswith(b"\xff\xd8")
    assert reloaded.create_qr_png(url).startswith(b"\x89PNG\r\n\x1a\n")


def test_unknown_and_malformed_tokens_are_rejected(tmp_path: Path) -> None:
    """Unknown and invalid token shapes provide no photo access."""
    _, _, downloads = _services(tmp_path)

    for token in ("unknown", "A" * 43):
        with pytest.raises(DownloadTokenNotFoundError):
            downloads.read_photo(token)


def test_expired_token_is_rejected_using_injected_clock(tmp_path: Path) -> None:
    """Expiration is checked against an injectable aware UTC clock."""
    now = [datetime(2026, 10, 25, tzinfo=timezone.utc)]
    gallery, photo_id, downloads = _services(tmp_path, lambda: now[0])
    token = downloads.create_token(photo_id)
    now[0] += timedelta(seconds=3600)

    reloaded = DownloadService(tmp_path / "data", gallery, 3600, lambda: now[0])
    with pytest.raises(DownloadTokenExpiredError):
        reloaded.read_photo(token.token)


def test_revoked_token_is_rejected_after_service_reload(tmp_path: Path) -> None:
    """Explicit revocation is persisted and enforced by later requests."""
    gallery, photo_id, downloads = _services(tmp_path)
    token = downloads.create_token(photo_id)
    downloads.revoke_token(token.token)
    reloaded = DownloadService(tmp_path / "data", gallery, 3600)

    with pytest.raises(DownloadTokenRevokedError):
        reloaded.read_photo(token.token)


def test_deleted_photo_invalidates_an_existing_download_token(tmp_path: Path) -> None:
    """Gallery deletion blocks every previously issued token for that photo."""
    gallery, photo_id, downloads = _services(tmp_path)
    token = downloads.create_token(photo_id)
    gallery.delete_photo(photo_id)

    with pytest.raises(DownloadTokenNotFoundError):
        downloads.read_photo(token.token)


def test_review_shows_qr_and_download_route_returns_attachment(tmp_path: Path) -> None:
    """Review embeds a QR and valid download responses hide internal paths."""
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            public_base_url="http://192.168.1.42:5000",
        ),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
    )
    app = create_app(configuration, SyntheticCameraBackend())
    client: FlaskClient = app.test_client()
    capture = client.post("/capture")
    assert capture.status_code == 200
    payload = capture.get_json()
    assert isinstance(payload, dict)
    review_url = cast(str, payload["review_url"])
    review = client.get(review_url)
    assert review.status_code == 200
    assert b"data:image/png;base64," in review.data
    assert b"Scannez ce QR code" in review.data
    assert b"Reprendre" in review.data
    assert b"Supprimer" in review.data
    assert b"Imprimer" in review.data

    photo_id = review_url.rsplit("/", maxsplit=1)[-1]
    downloads = cast(DownloadService, app.extensions["photobooth.downloads"])
    token = downloads.create_token(photo_id)
    response = client.get(f"/download/{token.token}")

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert "filename=photobooth-photo.jpg" in response.headers["Content-Disposition"]
    assert str(tmp_path).encode() not in response.data
    assert str(tmp_path) not in response.headers["Content-Disposition"]


def test_missing_public_base_url_shows_configuration_error_without_token(
    tmp_path: Path,
) -> None:
    """Local review remains usable but does not issue an unusable QR token."""
    configuration = ApplicationConfig(
        startup=StartupConfig(data_root=tmp_path / "data"),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
    )
    app = create_app(configuration, SyntheticCameraBackend())
    client: FlaskClient = app.test_client()
    capture = client.post("/capture")
    assert capture.status_code == 200
    payload = capture.get_json()
    assert isinstance(payload, dict)

    review = client.get(cast(str, payload["review_url"]))

    assert review.status_code == 200
    assert b"public_base_url must be configured" in review.data
    assert not (tmp_path / "data" / "metadata" / "download_tokens").exists()


def test_unknown_download_route_returns_not_found(tmp_path: Path) -> None:
    """The HTTP adapter conceals unknown and malformed bearer tokens as 404."""
    app = create_app(
        ApplicationConfig(
            startup=StartupConfig(data_root=tmp_path / "data"),
            booth=BoothSettings(countdown_seconds=0),
            config_path=tmp_path / "config.json",
        ),
        SyntheticCameraBackend(),
    )
    client: FlaskClient = app.test_client()

    assert client.get("/download/not-a-token").status_code == 404