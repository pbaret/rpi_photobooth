"""Load and persist validated photobooth configuration."""

import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, cast


class ConfigurationError(ValueError):
    """Report invalid or unreadable application configuration."""


class CameraBackend(str, Enum):
    """Select the camera implementation used by the application."""

    SYNTHETIC = "synthetic"
    OPENCV = "opencv"
    RPICAM = "rpicam"


@dataclass(frozen=True)
class StartupConfig:
    """Hold deployment settings that take effect when the process starts."""

    bind_host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    data_root: Path = Path("data")
    camera_backend: CameraBackend = CameraBackend.SYNTHETIC
    admin_secret: str | None = None

    def __post_init__(self) -> None:
        """Reject invalid values before they reach application setup."""
        if not self.bind_host.strip():
            raise ConfigurationError("bind_host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("port must be between 1 and 65535")
        if self.debug and self.bind_host in {"0.0.0.0", "::"}:
            raise ConfigurationError("debug mode cannot bind to a LAN interface")


@dataclass(frozen=True)
class BoothSettings:
    """Hold validated booth options stored in the runtime JSON file."""

    booth_name: str = "Photobooth"
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
    environ: Mapping[str, str] | None = None,
) -> ApplicationConfig:
    """Load defaults, persisted booth options, then startup environment overrides.

    The JSON file contains only booth settings. Environment variables configure
    process-level settings and therefore never overwrite persisted booth values.
    A missing JSON file is a normal first-run condition and is not created here.
    """
    environment = os.environ if environ is None else environ
    data_root = Path(environment.get("PHOTOBOOTH_DATA_ROOT", "data"))
    selected_path = config_path or data_root / "config.json"
    booth = _load_booth_settings(selected_path)
    startup = StartupConfig(
        bind_host=environment.get("PHOTOBOOTH_BIND_HOST", "127.0.0.1"),
        port=_environment_int(environment, "PHOTOBOOTH_PORT", 5000),
        debug=_environment_bool(environment, "PHOTOBOOTH_DEBUG", False),
        data_root=data_root,
        camera_backend=_environment_camera_backend(environment),
        admin_secret=environment.get("PHOTOBOOTH_ADMIN_SECRET"),
    )
    return ApplicationConfig(startup=startup, booth=booth, config_path=selected_path)


def save_booth_settings(config_path: Path, settings: BoothSettings) -> None:
    """Atomically persist validated booth settings without storing secrets.

    The temporary file is created beside the destination so replacement stays
    on the same filesystem. If writing or replacement fails, the prior file is
    left intact and the temporary file is removed when possible.
    """
    payload = {
        "booth_name": settings.booth_name,
        "countdown_seconds": settings.countdown_seconds,
        "idle_timeout_seconds": settings.idle_timeout_seconds,
        "slideshow_enabled": settings.slideshow_enabled,
        "slideshow_interval_seconds": settings.slideshow_interval_seconds,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _load_booth_settings(config_path: Path) -> BoothSettings:
    """Decode a booth settings file or return defaults when it is absent."""
    if not config_path.exists():
        return BoothSettings()
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            decoded: object = json.load(config_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot read configuration file: {config_path}") from error

    if not isinstance(decoded, dict):
        raise ConfigurationError("configuration file must contain a JSON object")
    raw_settings = cast(dict[object, object], decoded)
    values: dict[str, object] = {}
    for key, value in raw_settings.items():
        if not isinstance(key, str):
            raise ConfigurationError("configuration keys must be strings")
        values[key] = value

    supported_keys = {
        "booth_name",
        "countdown_seconds",
        "idle_timeout_seconds",
        "slideshow_enabled",
        "slideshow_interval_seconds",
    }
    unknown_keys = values.keys() - supported_keys
    if unknown_keys:
        unknown_key = sorted(unknown_keys)[0]
        raise ConfigurationError(f"unknown configuration setting: {unknown_key}")
    return BoothSettings(
        booth_name=_string_value(values, "booth_name", "Photobooth"),
        countdown_seconds=_integer_value(values, "countdown_seconds", 3),
        idle_timeout_seconds=_integer_value(values, "idle_timeout_seconds", 120),
        slideshow_enabled=_boolean_value(values, "slideshow_enabled", True),
        slideshow_interval_seconds=_integer_value(
            values, "slideshow_interval_seconds", 5
        ),
    )


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


def _environment_int(
    environ: Mapping[str, str], name: str, default: int
) -> int:
    """Parse an integer environment value with a setting-specific error."""
    value = environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error


def _environment_bool(
    environ: Mapping[str, str], name: str, default: bool
) -> bool:
    """Parse only the conventional true and false environment spellings."""
    value = environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _environment_camera_backend(environ: Mapping[str, str]) -> CameraBackend:
    """Parse the allowlisted camera backend environment value."""
    value = environ.get("PHOTOBOOTH_CAMERA_BACKEND", CameraBackend.SYNTHETIC.value)
    try:
        return CameraBackend(value)
    except ValueError as error:
        raise ConfigurationError(f"unknown camera backend: {value}") from error