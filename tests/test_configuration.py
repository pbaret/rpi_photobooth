"""Behavioral tests for configuration loading and persistence."""

import json
from pathlib import Path

import pytest

from photobooth.config import (
    ApplicationConfig,
    BoothSettings,
    CameraBackend,
    ConfigurationError,
    StartupConfig,
    load_configuration,
    save_booth_settings,
)


def test_defaults_are_used_without_configuration_file(tmp_path: Path) -> None:
    """First startup uses defaults and does not create persistence files."""
    config_path = tmp_path / "config.json"

    configuration = load_configuration(config_path)

    assert isinstance(configuration, ApplicationConfig)
    assert configuration.booth == BoothSettings()
    assert configuration.startup.bind_host == "127.0.0.1"
    assert configuration.startup.port == 5000
    assert configuration.startup.camera_backend is CameraBackend.SYNTHETIC
    assert configuration.startup.public_base_url is None
    assert configuration.startup.download_token_lifetime_seconds == 3600
    assert not config_path.exists()


def test_default_path_loads_config_json_from_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup reads config.json from the process working directory by default."""
    monkeypatch.chdir(tmp_path)
    Path("config.json").write_text(
        json.dumps({"startup": {"port": 8081}}), encoding="utf-8"
    )

    configuration = load_configuration()

    assert configuration.config_path == Path("config.json")
    assert configuration.startup.port == 8081


def test_startup_settings_are_loaded_from_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON provides operational settings while the admin secret comes from env."""
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_SECRET", "deployment-secret")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "startup": {
                    "bind_host": "0.0.0.0",
                    "port": 8080,
                    "debug": False,
                    "data_root": str(tmp_path / "photos"),
                    "camera_backend": "opencv",
                    "admin_secret": "local-secret",
                    "public_base_url": "http://192.168.1.42:5000",
                    "download_token_lifetime_seconds": 900,
                },
                "booth": {"booth_name": "Family booth"},
            }
        ),
        encoding="utf-8",
    )

    configuration = load_configuration(config_path)

    assert configuration.startup.bind_host == "0.0.0.0"
    assert configuration.startup.port == 8080
    assert not configuration.startup.debug
    assert configuration.startup.data_root == tmp_path / "photos"
    assert configuration.startup.camera_backend is CameraBackend.OPENCV
    assert configuration.startup.admin_secret == "deployment-secret"
    assert configuration.startup.public_base_url == "http://192.168.1.42:5000"
    assert configuration.startup.download_token_lifetime_seconds == 900
    assert configuration.booth.booth_name == "Family booth"


@pytest.mark.parametrize(
    "public_base_url",
    ["ftp://photobooth.local", "http://photobooth.local/booth", "http://user@host"],
)
def test_invalid_public_base_url_is_rejected(public_base_url: str) -> None:
    """Configured QR origins must be valid application HTTP(S) origins."""
    with pytest.raises(ConfigurationError, match="public_base_url"):
        StartupConfig(public_base_url=public_base_url)


def test_valid_json_overrides_booth_defaults(tmp_path: Path) -> None:
    """Recognized and correctly typed JSON values replace booth defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "booth_name": "Family booth",
                "countdown_seconds": 0,
                "slideshow_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    configuration = load_configuration(config_path)

    assert configuration.booth == BoothSettings(
        booth_name="Family booth",
        countdown_seconds=0,
        slideshow_enabled=False,
    )


def test_malformed_json_fails_without_overwriting_source(tmp_path: Path) -> None:
    """Malformed persisted data is reported and retained for diagnosis."""
    config_path = tmp_path / "config.json"
    original = b'{"countdown_seconds":'
    config_path.write_bytes(original)

    with pytest.raises(ConfigurationError, match="cannot read configuration file"):
        load_configuration(config_path)

    assert config_path.read_bytes() == original


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("countdown_seconds", -1),
        ("countdown_seconds", 31),
        ("idle_timeout_seconds", -1),
        ("slideshow_interval_seconds", 0),
    ],
)
def test_numeric_bounds_are_validated(
    tmp_path: Path, setting: str, value: int
) -> None:
    """Out-of-range numeric settings fail at the configuration boundary."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({setting: value}), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=setting):
        load_configuration(config_path)


def test_unknown_configuration_section_is_rejected(tmp_path: Path) -> None:
    """Misspelled sections fail clearly rather than silently using defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"startpu": {"port": 8081}}), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unknown configuration section"):
        load_configuration(config_path)


def test_persistence_atomically_writes_settings(tmp_path: Path) -> None:
    """A complete settings document becomes the destination in one replacement."""
    config_path = tmp_path / "nested" / "config.json"
    settings = BoothSettings(booth_name="Studio", countdown_seconds=5)

    save_booth_settings(config_path, settings)

    configuration = load_configuration(config_path)
    assert configuration.booth == settings
    assert configuration.startup.port == 5000
    assert not list(config_path.parent.glob("*.tmp"))


def test_failed_atomic_replacement_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed final replacement leaves the previous configuration intact."""
    config_path = tmp_path / "config.json"
    original = b'{"booth_name": "Prior"}\n'
    config_path.write_bytes(original)

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        """Simulate a filesystem error at the atomic replacement boundary."""
        raise OSError("replacement failed")

    monkeypatch.setattr("photobooth.config.os.replace", fail_replace)

    with pytest.raises(OSError, match="replacement failed"):
        save_booth_settings(config_path, BoothSettings(booth_name="New"))

    assert config_path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tmp"))


def test_booth_save_preserves_settings_without_persisting_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Updating booth settings retains operational values but omits secrets."""
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_SECRET", "deployment-secret")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "startup": {
                    "port": 8080,
                    "admin_secret": "local-secret",
                    "public_base_url": "http://192.168.1.42:5000",
                    "download_token_lifetime_seconds": 900,
                },
                "booth": {"booth_name": "Before"},
            }
        ),
        encoding="utf-8",
    )

    save_booth_settings(config_path, BoothSettings(booth_name="After"))

    configuration = load_configuration(config_path)
    assert configuration.startup.port == 8080
    assert configuration.startup.admin_secret == "deployment-secret"
    assert configuration.startup.public_base_url == "http://192.168.1.42:5000"
    assert configuration.startup.download_token_lifetime_seconds == 900
    assert configuration.booth.booth_name == "After"
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "admin_secret" not in persisted["startup"]