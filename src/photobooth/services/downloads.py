"""Manage temporary local download capabilities for gallery photos.

DownloadService stores one JSON record per cryptographically random token in
the existing metadata tree. Every resolution checks both token state and the
gallery, so deleting a photo invalidates its tokens without relying on cleanup.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from typing import cast

import qrcode

from photobooth.config import validate_public_base_url
from photobooth.services.gallery import GalleryService, PhotoNotFoundError


class DownloadError(Exception):
    """Base class for controlled download capability failures."""


class DownloadTokenError(DownloadError):
    """Report a token that does not grant access to a photo."""


class DownloadTokenNotFoundError(DownloadTokenError):
    """Report an unknown or malformed token without revealing which condition applied."""


class DownloadTokenExpiredError(DownloadTokenError):
    """Report a token whose configured lifetime has elapsed."""


class DownloadTokenRevokedError(DownloadTokenError):
    """Report a token explicitly revoked by the application."""


class DownloadStorageError(DownloadError):
    """Report unreadable or unwritable token metadata without exposing paths."""


@dataclass(frozen=True)
class DownloadToken:
    """Describe a persisted bearer capability and its single photo association."""

    token: str
    photo_id: str
    expires_at: datetime
    revoked: bool


class DownloadService:
    """Issue, persist, revoke, and resolve temporary photo download tokens.

    Tokens are independent of photo IDs and filenames. Each token expires at
    its persisted UTC deadline; revocation is persisted immediately. Photo
    deletion is enforced at resolution by asking GalleryService for the
    original bytes, even if token metadata remains on disk. The service is
    intended for the application's local single-process deployment model.
    """

    _TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")

    def __init__(
        self,
        data_root: Path,
        gallery: GalleryService,
        lifetime_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Select persistent token storage and the lifetime/clock policy.

        ``clock`` is injectable so expiration behavior can be tested without
        sleeping. The application owns token records; callers own the gallery.
        """
        if lifetime_seconds < 1:
            raise ValueError("download token lifetime must be positive")
        self._token_directory = data_root / "metadata" / "download_tokens"
        self._gallery = gallery
        self._lifetime = timedelta(seconds=lifetime_seconds)
        self._clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def create_token(self, photo_id: str) -> DownloadToken:
        """Persist a random token associated with one currently managed photo."""
        self._gallery.get_photo(photo_id)
        now = self._now()
        try:
            self._token_directory.mkdir(parents=True, exist_ok=True)
            while True:
                token = secrets.token_urlsafe(32)
                token_path = self._token_path(token)
                if not token_path.exists():
                    break
            record = DownloadToken(token, photo_id, now + self._lifetime, False)
            self._write_token(record)
            return record
        except OSError as error:
            raise DownloadStorageError("download token could not be stored") from error

    def read_photo(self, token: str) -> bytes:
        """Return original JPEG bytes only for an active token and managed photo."""
        record = self._read_token(token)
        if record.revoked:
            raise DownloadTokenRevokedError("download token is revoked")
        if self._now() >= record.expires_at:
            raise DownloadTokenExpiredError("download token has expired")
        try:
            return self._gallery.read_photo(record.photo_id)
        except PhotoNotFoundError as error:
            raise DownloadTokenNotFoundError("download photo is no longer available") from error

    def revoke_token(self, token: str) -> None:
        """Persist revocation; repeating revocation of a known token is harmless."""
        record = self._read_token(token)
        if record.revoked:
            return
        self._write_token(
            DownloadToken(record.token, record.photo_id, record.expires_at, True)
        )

    @staticmethod
    def build_download_url(token: str, public_base_url: str | None) -> str:
        """Build the absolute LAN URL without falling back to localhost."""
        if DownloadService._TOKEN_PATTERN.fullmatch(token) is None:
            raise DownloadTokenNotFoundError("download token is malformed")
        return f"{validate_public_base_url(public_base_url)}/download/{token}"

    @staticmethod
    def create_qr_png(download_url: str) -> bytes:
        """Encode one application download URL as a PNG QR image in memory."""
        image = qrcode.make(download_url)
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()

    def _read_token(self, token: str) -> DownloadToken:
        """Load and validate a token record without exposing storage details."""
        token_path = self._token_path(token)
        try:
            with token_path.open("r", encoding="utf-8") as token_file:
                document: object = json.load(token_file)
        except FileNotFoundError as error:
            raise DownloadTokenNotFoundError("download token is unknown") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DownloadStorageError("download token metadata cannot be read") from error

        if not isinstance(document, dict):
            raise DownloadStorageError("download token metadata is invalid")
        values = cast(dict[object, object], document)
        if set(values) != {"version", "token", "photo_id", "expires_at", "revoked"}:
            raise DownloadStorageError("download token metadata is invalid")
        version = values["version"]
        stored_token = values["token"]
        photo_id = values["photo_id"]
        expires_at_value = values["expires_at"]
        revoked = values["revoked"]
        if (
            type(version) is not int
            or version != 1
            or stored_token != token
            or not isinstance(photo_id, str)
            or type(revoked) is not bool
            or not isinstance(expires_at_value, str)
        ):
            raise DownloadStorageError("download token metadata is invalid")
        try:
            expires_at = datetime.fromisoformat(expires_at_value)
        except ValueError as error:
            raise DownloadStorageError("download token expiration is invalid") from error
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise DownloadStorageError("download token expiration is invalid")
        return DownloadToken(token, photo_id, expires_at, revoked)

    def _write_token(self, record: DownloadToken) -> None:
        """Atomically persist one token record without exposing its filesystem path."""
        self._token_directory.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._token_directory,
                prefix=".token.",
                suffix=".tmp",
                delete=False,
            ) as token_file:
                temporary_path = Path(token_file.name)
                json.dump(
                    {
                        "version": 1,
                        "token": record.token,
                        "photo_id": record.photo_id,
                        "expires_at": record.expires_at.isoformat(),
                        "revoked": record.revoked,
                    },
                    token_file,
                    separators=(",", ":"),
                )
                token_file.flush()
                os.fsync(token_file.fileno())
            os.replace(temporary_path, self._token_path(record.token))
        except OSError as error:
            raise DownloadStorageError("download token metadata could not be saved") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _token_path(self, token: str) -> Path:
        """Derive a token record path only after strict opaque-token validation."""
        if self._TOKEN_PATTERN.fullmatch(token) is None:
            raise DownloadTokenNotFoundError("download token is unknown")
        return self._token_directory / f"{token}.json"

    def _now(self) -> datetime:
        """Return an aware UTC instant from the configured clock."""
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("download token clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)