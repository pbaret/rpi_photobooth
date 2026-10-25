"""Manage persistent photos, their metadata, and slideshow thumbnails.

GalleryService owns application-controlled storage below the configured data
root. JSON metadata is the publication marker: a photo is available only once
its original, thumbnail, and metadata have all been atomically published.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
from typing import cast

from PIL import Image, UnidentifiedImageError


class GalleryError(Exception):
    """Base class for controlled gallery failures exposed to application code."""


class PhotoNotFoundError(GalleryError):
    """Report that an opaque photo identifier is unknown or no longer managed."""


class InvalidPhotoError(GalleryError):
    """Report that a captured source is not a readable JPEG image."""


class GalleryMetadataError(GalleryError):
    """Report malformed or inconsistent persisted JSON metadata."""


class GalleryStorageError(GalleryError):
    """Report a storage operation failure without exposing filesystem details."""


@dataclass(frozen=True)
class PhotoMetadata:
    """Describe one published photo without exposing its storage locations."""

    photo_id: str
    captured_at: datetime
    width: int
    height: int


class GalleryService:
    """Own photo identity, local JSON metadata, originals, and thumbnails.

    Metadata is written after the image and thumbnail and serves as the
    availability marker. Missing metadata means the photo is not managed;
    malformed metadata is reported as GalleryMetadataError. Deletion removes
    metadata first, immediately making all media lookups unavailable. If later
    file cleanup fails, inaccessible orphan files may remain for manual cleanup.
    """

    _PHOTO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{24}\Z")
    _THUMBNAIL_SIZE = (480, 360)

    def __init__(self, data_root: Path) -> None:
        """Select application-owned storage directories below ``data_root``."""
        self._photos_directory = data_root / "photos"
        self._thumbnails_directory = data_root / "thumbnails"
        self._metadata_directory = data_root / "metadata"

    def register_captured_photo(self, source_path: Path) -> PhotoMetadata:
        """Validate and atomically publish a captured JPEG and its metadata.

        The caller owns and may remove ``source_path``. A failed validation or
        publication leaves no photo addressable through this service; cleanup
        of any partial final files is attempted before GalleryStorageError is
        raised.
        """
        self._ensure_directories()
        try:
            width, height = self._image_dimensions(source_path)
        except InvalidPhotoError:
            raise
        except OSError as error:
            raise InvalidPhotoError("captured image cannot be read") from error

        photo_id = self._new_photo_id()
        metadata = PhotoMetadata(photo_id, datetime.now(timezone.utc), width, height)
        photo_path = self._photo_path(photo_id)
        thumbnail_path = self._thumbnail_path(photo_id)
        metadata_path = self._metadata_path(photo_id)
        temporary_paths: list[Path] = []
        published_paths: list[Path] = []
        try:
            staged_photo = self._temporary_path(self._photos_directory, photo_id)
            temporary_paths.append(staged_photo)
            shutil.copyfile(source_path, staged_photo)
            copied_width, copied_height = self._image_dimensions(staged_photo)
            if (copied_width, copied_height) != (width, height):
                raise InvalidPhotoError("captured image changed during publication")

            staged_thumbnail = self._temporary_path(
                self._thumbnails_directory, photo_id
            )
            temporary_paths.append(staged_thumbnail)
            self._write_thumbnail(staged_photo, staged_thumbnail)

            staged_metadata = self._temporary_path(self._metadata_directory, photo_id)
            temporary_paths.append(staged_metadata)
            self._write_metadata(staged_metadata, metadata)

            os.replace(staged_photo, photo_path)
            published_paths.append(photo_path)
            os.replace(staged_thumbnail, thumbnail_path)
            published_paths.append(thumbnail_path)
            os.replace(staged_metadata, metadata_path)
            published_paths.append(metadata_path)
            return metadata
        except InvalidPhotoError:
            self._remove_paths(published_paths)
            raise
        except (OSError, UnidentifiedImageError, ValueError) as error:
            self._remove_paths(published_paths)
            raise GalleryStorageError("photo could not be published") from error
        finally:
            self._remove_paths(temporary_paths)

    def get_photo(self, photo_id: str) -> PhotoMetadata:
        """Resolve valid metadata and require its original image to exist."""
        metadata = self._read_metadata(photo_id)
        if not self._photo_path(photo_id).is_file():
            raise GalleryStorageError("managed photo file is missing")
        return metadata

    def read_photo(self, photo_id: str) -> bytes:
        """Return original JPEG bytes for a currently managed photo."""
        self.get_photo(photo_id)
        try:
            return self._photo_path(photo_id).read_bytes()
        except OSError as error:
            raise GalleryStorageError("managed photo could not be read") from error

    def read_thumbnail(self, photo_id: str) -> bytes:
        """Return thumbnail bytes only while the photo remains managed."""
        self._read_metadata(photo_id)
        thumbnail_path = self._thumbnail_path(photo_id)
        try:
            return thumbnail_path.read_bytes()
        except FileNotFoundError as error:
            raise GalleryStorageError("managed photo thumbnail is missing") from error
        except OSError as error:
            raise GalleryStorageError("managed photo thumbnail could not be read") from error

    def delete_photo(self, photo_id: str) -> None:
        """Invalidate a photo before cleaning its original and thumbnail.

        Repeated deletion raises PhotoNotFoundError. If asset cleanup fails
        after metadata removal, the photo remains unavailable and orphan files
        may remain, but no media operation can resolve them as a gallery item.
        """
        self._read_metadata(photo_id)
        try:
            self._metadata_path(photo_id).unlink()
        except FileNotFoundError as error:
            raise PhotoNotFoundError("photo is not managed") from error
        except OSError as error:
            raise GalleryStorageError("photo could not be invalidated") from error

        try:
            self._photo_path(photo_id).unlink(missing_ok=True)
            self._thumbnail_path(photo_id).unlink(missing_ok=True)
        except OSError as error:
            raise GalleryStorageError("photo cleanup was incomplete") from error

    def _read_metadata(self, photo_id: str) -> PhotoMetadata:
        """Load validated metadata, distinguishing missing from malformed data."""
        self._validate_photo_id(photo_id)
        metadata_path = self._metadata_path(photo_id)
        try:
            with metadata_path.open("r", encoding="utf-8") as metadata_file:
                document: object = json.load(metadata_file)
        except FileNotFoundError as error:
            raise PhotoNotFoundError("photo is not managed") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GalleryMetadataError("photo metadata cannot be read") from error

        if not isinstance(document, dict):
            raise GalleryMetadataError("photo metadata must be a JSON object")
        values = cast(dict[object, object], document)
        expected_keys = {"version", "photo_id", "captured_at", "width", "height"}
        if set(values) != expected_keys:
            raise GalleryMetadataError("photo metadata has an invalid shape")
        version = values["version"]
        stored_id = values["photo_id"]
        captured_at_value = values["captured_at"]
        width = values["width"]
        height = values["height"]
        if version != 1 or type(version) is not int or stored_id != photo_id:
            raise GalleryMetadataError("photo metadata identity is invalid")
        if not isinstance(captured_at_value, str):
            raise GalleryMetadataError("photo metadata timestamp is invalid")
        if type(width) is not int or width < 1 or type(height) is not int or height < 1:
            raise GalleryMetadataError("photo metadata dimensions are invalid")
        try:
            captured_at = datetime.fromisoformat(captured_at_value)
        except ValueError as error:
            raise GalleryMetadataError("photo metadata timestamp is invalid") from error
        return PhotoMetadata(photo_id, captured_at, width, height)

    def _ensure_directories(self) -> None:
        """Create storage directories only when a capture is being published."""
        try:
            self._photos_directory.mkdir(parents=True, exist_ok=True)
            self._thumbnails_directory.mkdir(parents=True, exist_ok=True)
            self._metadata_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise GalleryStorageError("photo storage is unavailable") from error

    def _new_photo_id(self) -> str:
        """Allocate a URL-safe unpredictable identifier not already in storage."""
        while True:
            photo_id = secrets.token_urlsafe(18)
            if not any(
                path.exists()
                for path in (
                    self._photo_path(photo_id),
                    self._thumbnail_path(photo_id),
                    self._metadata_path(photo_id),
                )
            ):
                return photo_id

    def _validate_photo_id(self, photo_id: str) -> None:
        """Reject malformed client identifiers before deriving any paths."""
        if self._PHOTO_ID_PATTERN.fullmatch(photo_id) is None:
            raise PhotoNotFoundError("photo is not managed")

    def _photo_path(self, photo_id: str) -> Path:
        """Derive an original path after validating its application identifier."""
        self._validate_photo_id(photo_id)
        return self._photos_directory / f"{photo_id}.jpg"

    def _thumbnail_path(self, photo_id: str) -> Path:
        """Derive a thumbnail path after validating its application identifier."""
        self._validate_photo_id(photo_id)
        return self._thumbnails_directory / f"{photo_id}.jpg"

    def _metadata_path(self, photo_id: str) -> Path:
        """Derive a metadata path after validating its application identifier."""
        self._validate_photo_id(photo_id)
        return self._metadata_directory / f"{photo_id}.json"

    @staticmethod
    def _image_dimensions(image_path: Path) -> tuple[int, int]:
        """Verify JPEG integrity and return its dimensions without retaining it."""
        try:
            with Image.open(image_path) as image:
                if image.format != "JPEG":
                    raise InvalidPhotoError("captured image is not a JPEG")
                dimensions = image.size
                image.verify()
                return dimensions
        except InvalidPhotoError:
            raise
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise InvalidPhotoError("captured image is corrupt") from error

    @classmethod
    def _write_thumbnail(cls, source_path: Path, thumbnail_path: Path) -> None:
        """Create a bounded JPEG thumbnail suitable for later slideshow use."""
        try:
            with Image.open(source_path) as source:
                source.load()
                thumbnail = source.convert("RGB")
                thumbnail.thumbnail(cls._THUMBNAIL_SIZE)
                thumbnail.save(thumbnail_path, format="JPEG", quality=85)
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise InvalidPhotoError("captured image cannot produce a thumbnail") from error

    @staticmethod
    def _write_metadata(metadata_path: Path, metadata: PhotoMetadata) -> None:
        """Serialize one versioned JSON record to a staging file."""
        payload = {
            "version": 1,
            "photo_id": metadata.photo_id,
            "captured_at": metadata.captured_at.isoformat(),
            "width": metadata.width,
            "height": metadata.height,
        }
        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(payload, metadata_file, separators=(",", ":"))
            metadata_file.flush()
            os.fsync(metadata_file.fileno())

    @staticmethod
    def _temporary_path(directory: Path, photo_id: str) -> Path:
        """Reserve a unique staging filename in the destination filesystem."""
        with tempfile.NamedTemporaryFile(
            dir=directory,
            prefix=f".{photo_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            return Path(temporary_file.name)

    @staticmethod
    def _remove_paths(paths: list[Path]) -> None:
        """Best-effort cleanup for staged or partially published artifacts."""
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue