"""Load and persist validated photobooth configuration."""

import ipaddress
import json
import os
from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
import tempfile
from typing import cast
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Report invalid or unreadable application configuration."""


class CameraBackend(str, Enum):
    """Select the camera implementation used by the application."""

    SYNTHETIC = "synthetic"
    OPENCV = "opencv"
    RPICAM = "rpicam"


CameraSettingValue = bool | int | float | str


def _is_loopback_host(bind_host: str) -> bool:
    """Return whether a bind host is explicitly restricted to loopback."""
    if bind_host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind_host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class StartupConfig:
    """Hold deployment settings that take effect when the process starts."""

    bind_host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    data_root: Path = Path("data")
    camera_backend: CameraBackend = CameraBackend.SYNTHETIC
    camera_settings: dict[str, CameraSettingValue] = field(
        default_factory=lambda: dict[str, CameraSettingValue]()
    )
    admin_secret: str | None = None
    public_base_url: str | None = None
    download_token_lifetime_seconds: int = 3600

    def __post_init__(self) -> None:
        """Reject invalid values before they reach application setup."""
        if not self.bind_host.strip():
            raise ConfigurationError("bind_host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("port must be between 1 and 65535")
        if self.debug and not _is_loopback_host(self.bind_host):
            raise ConfigurationError("debug mode cannot bind to a LAN interface")
        if self.public_base_url is not None:
            validate_public_base_url(self.public_base_url)
        if self.download_token_lifetime_seconds < 1:
            raise ConfigurationError("download_token_lifetime_seconds must be positive")
        if any(
            not key
            or type(value) not in {bool, int, float, str}
            or (type(value) is float and not math.isfinite(value))
            for key, value in self.camera_settings.items()
        ):
            raise ConfigurationError("camera_settings must contain scalar values and non-empty keys")


@dataclass(frozen=True)
class BoothSettings:
    """Hold validated booth options stored in the runtime JSON file."""

    booth_name: str = "Photobooth"
    wifi_network_name: str = ""
    countdown_seconds: int = 3
    idle_timeout_seconds: int = 120
    slideshow_enabled: bool = True
    slideshow_interval_seconds: int = 5

    def __post_init__(self) -> None:
        """Reject empty labels and values outside the documented bounds."""
        if not self.booth_name.strip():
            raise ConfigurationError("booth_name must not be empty")
        if not 0 <= self.countdown_seconds <= 30:
            raise ConfigurationError("countdown_seconds must be between 0 and 30")
        if self.idle_timeout_seconds < 0:
            raise ConfigurationError("idle_timeout_seconds must not be negative")
        if self.slideshow_interval_seconds < 1:
            raise ConfigurationError("slideshow_interval_seconds must be positive")


@dataclass(frozen=True)
class ApplicationConfig:
    """Combine process startup settings with booth runtime settings."""

    startup: StartupConfig
    booth: BoothSettings
    config_path: Path


def load_configuration(
    config_path: Path | None = None,
) -> ApplicationConfig:
    """Load validated startup and booth settings from one JSON document.

    A missing file uses application defaults without creating a file. The
    default path is ``config.json`` in the process working directory.
    """
    selected_path = config_path or Path("config.json")
    document = read_json_object(selected_path)
    legacy_booth_keys = {
        "booth_name",
        "wifi_network_name",
        "countdown_seconds",
        "idle_timeout_seconds",
        "slideshow_enabled",
        "slideshow_interval_seconds",
    }
    is_legacy_document = document.keys() <= legacy_booth_keys
    if not is_legacy_document:
        unknown_sections = document.keys() - {"startup", "booth"}
        if unknown_sections:
            unknown_section = sorted(unknown_sections)[0]
            raise ConfigurationError(f"unknown configuration section: {unknown_section}")
    startup_values = _section_values(
        document,
        "startup",
        {
            "bind_host",
            "port",
            "debug",
            "data_root",
            "camera_backend",
            "camera_settings",
            "admin_secret",
            "public_base_url",
            "download_token_lifetime_seconds",
        },
    )
    booth_values = _section_values(
        document,
        "booth",
        {
            "booth_name",
            "wifi_network_name",
            "countdown_seconds",
            "idle_timeout_seconds",
            "slideshow_enabled",
            "slideshow_interval_seconds",
        },
    )
    data_root = Path(_string_value(startup_values, "data_root", "data"))
    startup = StartupConfig(
        bind_host=_string_value(startup_values, "bind_host", "127.0.0.1"),
        port=_integer_value(startup_values, "port", 5000),
        debug=_boolean_value(startup_values, "debug", False),
        data_root=data_root,
        camera_backend=_camera_backend_value(startup_values),
        camera_settings=_camera_settings_value(startup_values),
        admin_secret=os.environ.get("PHOTOBOOTH_ADMIN_SECRET"),
        public_base_url=_optional_string_value(startup_values, "public_base_url"),
        download_token_lifetime_seconds=_integer_value(
            startup_values, "download_token_lifetime_seconds", 3600
        ),
    )
    booth = BoothSettings(
        booth_name=_string_value(booth_values, "booth_name", "Photobooth"),
        wifi_network_name=_string_value(booth_values, "wifi_network_name", ""),
        countdown_seconds=_integer_value(booth_values, "countdown_seconds", 3),
        idle_timeout_seconds=_integer_value(booth_values, "idle_timeout_seconds", 120),
        slideshow_enabled=_boolean_value(booth_values, "slideshow_enabled", True),
        slideshow_interval_seconds=_integer_value(
            booth_values, "slideshow_interval_seconds", 5
        ),
    )
    return ApplicationConfig(startup=startup, booth=booth, config_path=selected_path)


def save_booth_settings(config_path: Path, settings: BoothSettings) -> None:
    """Atomically persist booth settings while retaining startup configuration.

    The temporary file is created beside the destination so replacement stays
    on the same filesystem. If writing or replacement fails, the prior file is
    left intact and the temporary file is removed when possible. Deployment
    secrets are never copied into the persisted document.
    """
    current = load_configuration(config_path)
    save_configuration(
        ApplicationConfig(
            startup=current.startup,
            booth=settings,
            config_path=config_path,
        )
    )


def save_configuration(configuration: ApplicationConfig) -> None:
    """Atomically persist validated settings without deployment secrets.

    Startup values that are part of the editable application configuration
    retain their existing names. ``admin_secret`` is deliberately sourced only
    from the deployment environment and is never serialized.
    """
    startup = configuration.startup
    settings = configuration.booth
    payload: dict[str, object] = {
        "startup": {
            "bind_host": startup.bind_host,
            "port": startup.port,
            "debug": startup.debug,
            "data_root": str(startup.data_root),
            "camera_backend": startup.camera_backend.value,
            "camera_settings": startup.camera_settings,
            "public_base_url": startup.public_base_url,
            "download_token_lifetime_seconds": startup.download_token_lifetime_seconds,
        },
        "booth": {
            "booth_name": settings.booth_name,
            "wifi_network_name": settings.wifi_network_name,
            "countdown_seconds": settings.countdown_seconds,
            "idle_timeout_seconds": settings.idle_timeout_seconds,
            "slideshow_enabled": settings.slideshow_enabled,
            "slideshow_interval_seconds": settings.slideshow_interval_seconds,
        },
    }
    write_json_atomically(configuration.config_path, payload)


def write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON document so readers see either the old or the new file.

    The temporary file is created beside the destination so replacement stays
    on the same filesystem. ``OSError`` is propagated after the temporary file
    is removed; the previous destination file is left untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def read_json_object(config_path: Path) -> dict[str, object]:
    """Decode a JSON object, treating a missing file as an empty document.

    Unreadable files, invalid JSON, non-object documents and non-string keys
    raise ``ConfigurationError``; a corrupt file is never silently replaced.
    """
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            decoded: object = json.load(config_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot read configuration file: {config_path}") from error

    if not isinstance(decoded, dict):
        raise ConfigurationError("configuration file must contain a JSON object")
    raw_values = cast(dict[object, object], decoded)
    values: dict[str, object] = {}
    for key, value in raw_values.items():
        if not isinstance(key, str):
            raise ConfigurationError("configuration keys must be strings")
        values[key] = value
    return values


def _section_values(
    document: dict[str, object], section_name: str, supported_keys: set[str]
) -> dict[str, object]:
    """Validate and return one named object section from the document.

    The prior format stored booth values at the document root; it remains
    readable so existing installations can move to the new schema gradually.
    """
    booth_keys = {
        "booth_name",
        "wifi_network_name",
        "countdown_seconds",
        "idle_timeout_seconds",
        "slideshow_enabled",
        "slideshow_interval_seconds",
    }
    if section_name == "booth" and "startup" not in document and "booth" not in document:
        section = {key: value for key, value in document.items() if key in booth_keys}
        unknown_keys = document.keys() - booth_keys
    else:
        raw_section = document.get(section_name, {})
        if not isinstance(raw_section, dict):
            raise ConfigurationError(f"{section_name} configuration must be a JSON object")
        section = cast(dict[str, object], raw_section)
        unknown_keys = section.keys() - supported_keys
    if unknown_keys:
        unknown_key = sorted(unknown_keys)[0]
        raise ConfigurationError(f"unknown {section_name} configuration setting: {unknown_key}")
    return section


def _string_value(values: dict[str, object], name: str, default: str) -> str:
    """Return a setting only if its external value is a string."""
    value = values.get(name, default)
    if not isinstance(value, str):
        raise ConfigurationError(f"{name} must be a string")
    return value


def _integer_value(values: dict[str, object], name: str, default: int) -> int:
    """Return a setting only if its external value is an integer, not a bool."""
    value = values.get(name, default)
    if type(value) is not int:
        raise ConfigurationError(f"{name} must be an integer")
    return value


def _boolean_value(values: dict[str, object], name: str, default: bool) -> bool:
    """Return a setting only if its external value is a JSON boolean."""
    value = values.get(name, default)
    if not isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a boolean")
    return value


def _camera_backend_value(values: dict[str, object]) -> CameraBackend:
    """Return the allowlisted camera backend selected in startup settings."""
    value = _string_value(values, "camera_backend", CameraBackend.SYNTHETIC.value)
    try:
        return CameraBackend(value)
    except ValueError as error:
        raise ConfigurationError(f"unknown camera backend: {value}") from error


def _camera_settings_value(values: dict[str, object]) -> dict[str, CameraSettingValue]:
    """Decode a scalar setting map while retaining backend-specific identifiers."""
    raw_settings = values.get("camera_settings", {})
    if not isinstance(raw_settings, dict):
        raise ConfigurationError("camera_settings must be an object")
    raw_mapping = cast(dict[object, object], raw_settings)
    settings: dict[str, CameraSettingValue] = {}
    for key, value in raw_mapping.items():
        if not isinstance(key, str) or not key:
            raise ConfigurationError("camera_settings keys must be non-empty strings")
        if type(value) is bool:
            settings[key] = value
        elif type(value) is int:
            settings[key] = value
        elif type(value) is float:
            if not math.isfinite(value):
                raise ConfigurationError(f"camera_settings.{key} must be finite")
            settings[key] = value
        elif isinstance(value, str):
            settings[key] = value
        else:
            raise ConfigurationError(f"camera_settings.{key} must be a scalar value")
    return settings


def _optional_string_value(values: dict[str, object], name: str) -> str | None:
    """Return a string or null optional startup value from JSON."""
    value = values.get(name)
    if value is not None and not isinstance(value, str):
        raise ConfigurationError(f"{name} must be a string or null")
    return value


def validate_public_base_url(public_base_url: str | None) -> str:
    """Return a normalized HTTP(S) origin suitable for application download links.

    Public URLs must identify this application's root without credentials,
    query parameters, or fragments. A missing URL is allowed at startup but
    raises a clear error when a QR download is requested.
    """
    if public_base_url is None or not public_base_url.strip():
        raise ConfigurationError(
            "public_base_url must be configured to generate download QR codes"
        )
    if public_base_url != public_base_url.strip():
        raise ConfigurationError("public_base_url must not contain surrounding whitespace")
    try:
        parsed = urlsplit(public_base_url)
        parsed.port
    except ValueError as error:
        raise ConfigurationError("public_base_url is invalid") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "public_base_url must be an HTTP(S) origin without credentials or a path"
        )
    return public_base_url.rstrip("/")