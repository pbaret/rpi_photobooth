"""Store and serve locally managed event background images.

BackgroundService owns ``data_root/backgrounds``. Uploaded bytes are decoded
with Pillow, normalized (EXIF orientation applied, longest edge bounded) and
re-encoded as JPEG, or PNG when transparency is present, under a random
application-controlled filename. Client filenames are never used and remote
URLs are not supported. Published images are immutable; changing the event
artwork means uploading a new image and selecting it in the theme.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
import secrets
import tempfile

from PIL import Image, ImageOps

from photobooth.theme import is_background_identifier


class BackgroundError(Exception):
    """Base class for controlled background-image failures."""


class BackgroundNotFoundError(BackgroundError):
    """Report an identifier that is malformed or not currently stored."""


class InvalidBackgroundError(BackgroundError):
    """Report uploaded bytes that are not a supported, decodable image."""


class BackgroundStorageError(BackgroundError):
    """Report a storage failure without exposing filesystem details."""


@dataclass(frozen=True)
class BackgroundImage:
    """Describe one stored background for administrator selection."""

    identifier: str
    uploaded_at: datetime


@dataclass(frozen=True)
class BackgroundContent:
    """Hold encoded background bytes and their HTTP media type."""

    data: bytes
    mimetype: str


class BackgroundService:
    """Own validation, naming, publication and lookup of event backgrounds.

    Files are published by atomic rename, so readers never observe partial
    images. The service holds no open resources and may be shared between
    request threads; concurrent uploads receive distinct random identifiers.
    """

    _ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
    _MAX_EDGE = 3840
    _MAX_SOURCE_PIXELS = 40_000_000
    _JPEG_QUALITY = 90

    def __init__(self, data_root: Path) -> None:
        """Select ``data_root/backgrounds`` without touching the filesystem."""
        self._directory = data_root / "backgrounds"

    def list_backgrounds(self) -> tuple[BackgroundImage, ...]:
        """Return stored backgrounds, most recently uploaded first.

        Files whose names are not managed identifiers are ignored. Raises
        ``BackgroundStorageError`` when the directory cannot be read.
        """
        if not self._directory.is_dir():
            return ()
        try:
            images = [
                BackgroundImage(
                    path.name,
                    datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
                )
                for path in self._directory.iterdir()
                if is_background_identifier(path.name) and path.is_file()
            ]
        except OSError as error:
            raise BackgroundStorageError("backgrounds cannot be listed") from error
        return tuple(sorted(images, key=lambda image: image.uploaded_at, reverse=True))

    def exists(self, identifier: str) -> bool:
        """Return whether ``identifier`` is well formed and currently stored."""
        return is_background_identifier(identifier) and (self._directory / identifier).is_file()

    def read(self, identifier: str) -> BackgroundContent:
        """Return stored bytes for a managed identifier.

        Raises ``BackgroundNotFoundError`` for malformed or absent identifiers
        and ``BackgroundStorageError`` for other read failures.
        """
        if not is_background_identifier(identifier):
            raise BackgroundNotFoundError("background is not managed")
        try:
            data = (self._directory / identifier).read_bytes()
        except FileNotFoundError as error:
            raise BackgroundNotFoundError("background is not managed") from error
        except OSError as error:
            raise BackgroundStorageError("background cannot be read") from error
        mimetype = "image/png" if identifier.endswith(".png") else "image/jpeg"
        return BackgroundContent(data, mimetype)

    def store(self, data: bytes) -> str:
        """Validate, normalize and publish uploaded image bytes.

        Returns the new identifier. Raises ``InvalidBackgroundError`` when the
        bytes are not a JPEG, PNG or WebP image within the pixel limit, and
        ``BackgroundStorageError`` when publication fails; no partial file is
        left behind in either case.
        """
        image = self._decode(data)
        has_alpha = image.mode in {"RGBA", "LA", "PA"} or (
            image.mode == "P" and "transparency" in image.info
        )
        converted = image.convert("RGBA" if has_alpha else "RGB")
        converted.thumbnail((self._MAX_EDGE, self._MAX_EDGE), Image.Resampling.LANCZOS)
        identifier = secrets.token_urlsafe(16) + (".png" if has_alpha else ".jpg")
        temporary_path: Path | None = None
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self._directory, prefix=".upload-", suffix=".tmp", delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                if has_alpha:
                    converted.save(temporary_file, format="PNG", optimize=True)
                else:
                    converted.save(
                        temporary_file, format="JPEG", quality=self._JPEG_QUALITY, optimize=True
                    )
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._directory / identifier)
            temporary_path = None
        except OSError as error:
            raise BackgroundStorageError("background cannot be stored") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return identifier

    @classmethod
    def _decode(cls, data: bytes) -> Image.Image:
        """Fully decode accepted formats, rejecting oversized or corrupt input."""
        try:
            with Image.open(BytesIO(data)) as probe:
                if probe.format not in cls._ACCEPTED_FORMATS:
                    raise InvalidBackgroundError("unsupported image format")
                if probe.width * probe.height > cls._MAX_SOURCE_PIXELS:
                    raise InvalidBackgroundError("image is too large")
                probe.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                return ImageOps.exif_transpose(source)
        except InvalidBackgroundError:
            raise
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
            raise InvalidBackgroundError("upload is not a readable image") from error
