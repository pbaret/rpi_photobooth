"""Behavioral tests for configuration loading and persistence."""

import json
from pathlib import Path

import pytest

from photobooth.config import (
    ApplicationConfig,
    BoothSettings,
    CameraBackend,
    ConfigurationError,
    load_configuration,
    save_booth_settings,
)


def test_defaults_are_used_without_configuration_file(tmp_path: Path) -> None:
    """First startup uses defaults and does not create persistence files."""
    config_path = tmp_path / "config.json"

    configuration = load_configuration(config_path, {})

    assert isinstance(configuration, ApplicationConfig)
    assert configuration.booth == BoothSettings()
    assert configuration.startup.bind_host == "127.0.0.1"
    assert configuration.startup.port == 5000
    assert configuration.startup.camera_backend is CameraBackend.SYNTHETIC
    assert not config_path.exists()


def test_environment_overrides_startup_settings(tmp_path: Path) -> None:
    """Environment values override deployment defaults without changing booth values."""
    configuration = load_configuration(
        tmp_path / "config.json",
        {
            "PHOTOBOOTH_BIND_HOST": "0.0.0.0",
            "PHOTOBOOTH_PORT": "8080",
            "PHOTOBOOTH_DEBUG": "false",
            "PHOTOBOOTH_DATA_ROOT": str(tmp_path),
            "PHOTOBOOTH_CAMERA_BACKEND": "opencv",
            "PHOTOBOOTH_ADMIN_SECRET": "local-secret",
        },
    )

    assert configuration.startup.bind_host == "0.0.0.0"
    assert configuration.startup.port == 8080
    assert not configuration.startup.debug
    assert configuration.startup.data_root == tmp_path
    assert configuration.startup.camera_backend is CameraBackend.OPENCV
    assert configuration.startup.admin_secret == "local-secret"
    assert configuration.booth == BoothSettings()


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

    configuration = load_configuration(config_path, {})

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
        load_configuration(config_path, {})

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
        load_configuration(config_path, {})


def test_persistence_atomically_writes_settings(tmp_path: Path) -> None:
    """A complete settings document becomes the destination in one replacement."""
    config_path = tmp_path / "nested" / "config.json"
    settings = BoothSettings(booth_name="Studio", countdown_seconds=5)

    save_booth_settings(config_path, settings)

    assert load_configuration(config_path, {}).booth == settings
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


def test_saved_booth_settings_do_not_include_startup_secrets(tmp_path: Path) -> None:
    """Runtime persistence cannot serialize deployment-only secret values."""
    config_path = tmp_path / "config.json"

    save_booth_settings(config_path, BoothSettings())

    assert "admin_secret" not in config_path.read_text(encoding="utf-8")