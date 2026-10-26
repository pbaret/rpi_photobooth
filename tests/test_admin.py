"""Behavioral tests for protected runtime administration."""

import base64
import json
from pathlib import Path
from typing import cast

from flask import Flask
import pytest

from photobooth.app import create_app
from photobooth.camera import OpenCVCameraBackend
from photobooth.config import (
    ApplicationConfig,
    BoothSettings,
    CameraBackend as CameraBackendKind,
    StartupConfig,
)
from photobooth.services.preview import PreviewService


def test_admin_requires_valid_basic_authentication(tmp_path: Path) -> None:
    """Only the configured administrator credential opens the page."""
    client = _app(tmp_path).test_client()

    assert client.get("/admin").status_code == 401
    invalid = client.get("/admin", headers=_auth_header("wrong-secret"))
    assert invalid.status_code == 401
    assert 'Basic realm="Photobooth administration"' in invalid.headers["WWW-Authenticate"]

    valid = client.get("/admin", headers=_auth_header("deployment-secret"))
    assert valid.status_code == 200
    assert b"Photobooth administration" in valid.data
    assert b"deployment-secret" not in valid.data


def test_admin_is_unavailable_without_a_deployment_secret(tmp_path: Path) -> None:
    """The admin interface fails closed when no secret is configured."""
    client = _app(tmp_path, secret=None).test_client()

    response = client.get("/admin", headers=_auth_header("anything"))

    assert response.status_code == 503
    assert b"not configured" in response.data


def test_admin_authentication_accepts_unicode_environment_secrets(
    tmp_path: Path,
) -> None:
    """UTF-8 byte comparison supports non-ASCII deployment secrets."""
    client = _app(tmp_path, secret="café-secret").test_client()

    response = client.get("/admin", headers=_auth_header("café-secret"))

    assert response.status_code == 200


def test_valid_update_applies_live_values_and_reports_camera_restart(
    tmp_path: Path,
) -> None:
    """Booth and download settings apply now; backend selection remains saved only."""
    app = _app(tmp_path)
    client = app.test_client()
    form = _form(
        booth_name="Studio booth",
        countdown_seconds="8",
        slideshow_enabled="false",
        public_base_url="http://booth.local:5000",
        download_token_lifetime_seconds="60",
        camera_backend="opencv",
    )

    response = client.post(
        "/admin/settings", data=form, headers=_auth_header("deployment-secret")
    )

    assert response.status_code == 303
    page = client.get(response.headers["Location"], headers=_auth_header("deployment-secret"))
    assert page.status_code == 200
    assert b"requires an application restart" in page.data
    assert b"Active camera backend</dt><dd>synthetic" in page.data
    assert b"Saved camera backend</dt><dd>opencv" in page.data
    booth_page = client.get("/")
    assert b'data-countdown-seconds="8"' in booth_page.data
    assert b'data-slideshow-enabled="false"' in booth_page.data
    assert b"Studio booth" in booth_page.data

    effective = cast(ApplicationConfig, app.extensions["photobooth.configuration"])
    persisted = cast(
        ApplicationConfig, app.extensions["photobooth.persisted_configuration"]
    )
    assert effective.startup.camera_backend.value == "synthetic"
    assert effective.startup.public_base_url == "http://booth.local:5000"
    assert effective.startup.download_token_lifetime_seconds == 60
    assert effective.booth.countdown_seconds == 8
    assert persisted.startup.camera_backend.value == "opencv"
    stored = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert stored["startup"]["camera_backend"] == "opencv"
    assert "admin_secret" not in stored["startup"]
    assert "deployment-secret" not in json.dumps(stored)
    _close_preview(app)


def test_invalid_update_preserves_prior_configuration_and_submitted_value(
    tmp_path: Path,
) -> None:
    """An invalid field neither changes memory nor creates a partial config file."""
    config_path = tmp_path / "config.json"
    original = b'{"booth":{"booth_name":"Prior valid name"}}\n'
    config_path.write_bytes(original)
    configuration = ApplicationConfig(
        startup=StartupConfig(data_root=tmp_path / "data", admin_secret="deployment-secret"),
        booth=BoothSettings(booth_name="Prior valid name"),
        config_path=config_path,
    )
    app = create_app(configuration=configuration)
    client = app.test_client()

    response = client.post(
        "/admin/settings",
        data=_form(booth_name="Partial replacement", countdown_seconds="31"),
        headers=_auth_header("deployment-secret"),
    )

    assert response.status_code == 400
    assert b"countdown_seconds" in response.data
    assert b'value="31"' in response.data
    assert config_path.read_bytes() == original
    effective = cast(ApplicationConfig, app.extensions["photobooth.configuration"])
    assert effective.booth == BoothSettings(booth_name="Prior valid name")
    _close_preview(app)


def test_admin_save_failure_keeps_existing_file_and_active_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomic replacement failure leaves disk and effective configuration intact."""
    config_path = tmp_path / "config.json"
    original = b'{"booth":{"booth_name":"Prior"}}\n'
    config_path.write_bytes(original)
    app = _app(tmp_path, config_path=config_path)
    client = app.test_client()

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        """Fail at the atomic file replacement boundary."""
        raise OSError("private filesystem detail")

    monkeypatch.setattr("photobooth.config.os.replace", fail_replace)
    response = client.post(
        "/admin/settings",
        data=_form(booth_name="Changed"),
        headers=_auth_header("deployment-secret"),
    )

    assert response.status_code == 500
    assert b"private filesystem detail" not in response.data
    assert config_path.read_bytes() == original
    effective = cast(ApplicationConfig, app.extensions["photobooth.configuration"])
    assert effective.booth.booth_name == "Photobooth"
    assert not list(tmp_path.glob(".*.tmp"))
    _close_preview(app)


def test_admin_updates_are_post_only_and_diagnostics_are_non_sensitive(
    tmp_path: Path,
) -> None:
    """Diagnostics expose operational counts and never include administrator secrets."""
    client = _app(tmp_path).test_client()
    headers = _auth_header("deployment-secret")

    assert client.get("/admin/settings", headers=headers).status_code == 405
    response = client.get("/admin", headers=headers)

    assert b"Managed photos</dt><dd>0" in response.data
    assert b"Active camera backend</dt><dd>synthetic" in response.data
    assert b"NullPrinterBackend" in response.data
    assert b"deployment-secret" not in response.data
    assert b"download_tokens" not in response.data
    assert b"config.json" not in response.data


def test_camera_controls_render_from_synthetic_capabilities(tmp_path: Path) -> None:
    """The active synthetic backend chooses native controls and read-only presentation."""
    client = _app(tmp_path).test_client()
    response = client.get("/admin", headers=_auth_header("deployment-secret"))

    assert response.status_code == 200
    assert b'name="camera_setting_synthetic_overlay" type="checkbox"' in response.data
    assert b'name="camera_setting_synthetic_quality" type="number"' in response.data
    assert b'name="camera_setting_synthetic_scene"' in response.data
    assert b'id="camera_setting_synthetic_running" class="readonly-value"' in response.data
    assert b"Requested: Not applicable. Effective: False." in response.data
    assert b'camera_setting_preview_width' not in response.data
    assert b'Changing this setting requires a camera restart.' in response.data


def test_live_camera_value_is_persisted_and_reported_as_effective(tmp_path: Path) -> None:
    """A validated live synthetic control updates requested and effective values."""
    app = _app(tmp_path)
    client = app.test_client()
    response = client.post(
        "/admin/settings",
        data=_form(camera_settings_present="true", camera_setting_synthetic_overlay="true"),
        headers=_auth_header("deployment-secret"),
    )

    assert response.status_code == 303
    page = client.get(response.headers["Location"], headers=_auth_header("deployment-secret"))
    assert b"Requested: True. Effective: True." in page.data
    persisted = cast(ApplicationConfig, app.extensions["photobooth.persisted_configuration"])
    effective = cast(ApplicationConfig, app.extensions["photobooth.configuration"])
    assert persisted.startup.camera_settings["synthetic_overlay"] is True
    assert effective.startup.camera_settings["synthetic_overlay"] is True
    _close_preview(app)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("synthetic_quality", "31"),
        ("synthetic_scene", "not-declared"),
        ("synthetic_running", "true"),
    ],
)
def test_invalid_camera_values_are_rejected_without_persistence(
    tmp_path: Path, field: str, value: str
) -> None:
    """Bounds, enum membership, and read-only declarations are enforced server-side."""
    app = _app(tmp_path)
    client = app.test_client()
    configuration_path = cast(
        ApplicationConfig, app.extensions["photobooth.persisted_configuration"]
    ).config_path

    response = client.post(
        "/admin/settings",
        data=_form(**{f"camera_setting_{field}": value}),
        headers=_auth_header("deployment-secret"),
    )

    assert response.status_code == 400
    assert field.encode() in response.data
    assert not configuration_path.exists()
    _close_preview(app)


def test_restart_setting_keeps_requested_and_effective_values_distinct(
    tmp_path: Path,
) -> None:
    """A restart-required request is saved without claiming that the backend applied it."""
    app = _app(tmp_path)
    client = app.test_client()
    response = client.post(
        "/admin/settings",
        data=_form(camera_setting_synthetic_scene="colorful"),
        headers=_auth_header("deployment-secret"),
    )

    assert response.status_code == 303
    page = client.get(response.headers["Location"], headers=_auth_header("deployment-secret"))
    assert b"Requested: colorful. Effective: classic." in page.data
    assert b"requires a camera restart" in page.data
    persisted = cast(ApplicationConfig, app.extensions["photobooth.persisted_configuration"])
    effective = cast(ApplicationConfig, app.extensions["photobooth.configuration"])
    assert persisted.startup.camera_settings["synthetic_scene"] == "colorful"
    assert effective.startup.camera_settings.get("synthetic_scene") is None
    _close_preview(app)


def test_unsupported_camera_setting_is_preserved_but_not_rendered(tmp_path: Path) -> None:
    """Synthetic ignores OpenCV/future requests without deleting or presenting them."""
    settings: dict[str, bool | int | float | str] = {
        "preview_width": 1280,
        "future_control": "retain-me",
    }
    configuration_path = tmp_path / "config.json"
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret="deployment-secret",
            camera_settings=settings,
        ),
        booth=BoothSettings(),
        config_path=configuration_path,
    )
    app = create_app(configuration=configuration)
    client = app.test_client()

    page = client.get("/admin", headers=_auth_header("deployment-secret"))
    assert page.status_code == 200
    assert b"camera_setting_preview_width" not in page.data
    response = client.post(
        "/admin/settings", data=_form(), headers=_auth_header("deployment-secret")
    )
    assert response.status_code == 303
    stored = json.loads(configuration_path.read_text(encoding="utf-8"))
    assert stored["startup"]["camera_settings"] == settings
    _close_preview(app)


def test_opencv_admin_exposes_only_declared_controls(tmp_path: Path) -> None:
    """OpenCV presents implemented dimensions and software mirror, not synthetic or future controls."""
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret="deployment-secret",
            camera_backend=CameraBackendKind.OPENCV,
        ),
        booth=BoothSettings(),
        config_path=tmp_path / "config.json",
    )
    app = create_app(configuration=configuration, camera_backend=OpenCVCameraBackend())
    client = app.test_client()
    page = client.get("/admin", headers=_auth_header("deployment-secret"))

    assert page.status_code == 200
    assert b"camera_setting_preview_width" in page.data
    assert b"camera_setting_preview_height" in page.data
    assert b"camera_setting_preview_mirror" in page.data
    assert b"camera_setting_synthetic_overlay" not in page.data
    assert b"autofocus" not in page.data
    assert b"One or more camera settings are saved as requested" not in page.data
    _close_preview(app)


def test_blank_url_is_allowed_and_invalid_url_is_reported(tmp_path: Path) -> None:
    """URL validation is server-side and a blank optional value remains valid."""
    client = _app(tmp_path).test_client()
    headers = _auth_header("deployment-secret")

    blank_url = client.post("/admin/settings", data=_form(), headers=headers)
    assert blank_url.status_code == 303

    invalid_url = client.post(
        "/admin/settings",
        data=_form(public_base_url="ftp://invalid.example"),
        headers=headers,
    )
    assert invalid_url.status_code == 400
    assert b"public_base_url" in invalid_url.data


def _app(
    tmp_path: Path,
    secret: str | None = "deployment-secret",
    config_path: Path | None = None,
) -> Flask:
    """Build an isolated synthetic-camera app with explicit admin settings."""
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret=secret,
        ),
        booth=BoothSettings(),
        config_path=config_path if config_path is not None else tmp_path / "config.json",
    )
    return create_app(configuration=configuration)


def _auth_header(secret: str) -> dict[str, str]:
    """Encode the fixed admin username and supplied password as Basic auth."""
    credential = base64.b64encode(f"admin:{secret}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {credential}"}


def _form(**overrides: str) -> dict[str, str]:
    """Return a complete valid update payload with selected overrides."""
    values = {
        "booth_name": "Photobooth",
        "countdown_seconds": "3",
        "idle_timeout_seconds": "120",
        "slideshow_interval_seconds": "5",
        "slideshow_enabled": "true",
        "public_base_url": "",
        "download_token_lifetime_seconds": "3600",
        "camera_backend": "synthetic",
    }
    values.update(overrides)
    return values


def _close_preview(app: Flask) -> None:
    """Release the application-owned preview service after the test."""
    preview = cast(PreviewService, app.extensions["photobooth.preview"])
    preview.close()