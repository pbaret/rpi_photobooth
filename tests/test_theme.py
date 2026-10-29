"""Behavioral tests for the event theme model, background storage and theming."""

import base64
from io import BytesIO
import json
from pathlib import Path
from typing import cast

from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
import pytest

from photobooth.app import create_app
from photobooth.camera.synthetic import SyntheticCameraBackend
from photobooth.config import (
    ApplicationConfig,
    BoothSettings,
    ConfigurationError,
    StartupConfig,
)
from photobooth.services.backgrounds import BackgroundService, InvalidBackgroundError
from photobooth.services.preview import PreviewService
from photobooth.theme import (
    BackgroundFit,
    BackgroundPosition,
    HeroPosition,
    HeroSize,
    PreviewFit,
    PreviewLayout,
    ReviewLayout,
    ThemeColors,
    ThemeSettings,
    WidgetAnchor,
    load_theme,
    parse_theme,
    save_theme,
    theme_path_for,
)

_SECRET = "deployment-secret"


def test_default_theme_is_complete_and_maps_to_css(tmp_path: Path) -> None:
    """A missing theme file yields the documented defaults without creating a file."""
    path = tmp_path / "theme.json"

    theme = load_theme(path)

    assert theme == ThemeSettings()
    assert not path.exists()
    assert theme.css_variables() == {
        "--booth-background-color": "#111316",
        "--booth-surface-color": "#1f2328",
        "--booth-foreground-color": "#f5f1e8",
        "--booth-primary-color": "#f2b544",
        "--booth-primary-text-color": "#15171a",
        "--booth-background-fit": "cover",
        "--booth-background-position": "center",
    }
    assert theme.preview.stage_classes == "hero-left hero-size-large hero-fit-contain"
    assert theme.review.stage_classes == "hero-left hero-size-medium hero-fit-contain"
    assert theme.preview.capture_position.css_classes == "anchor anchor-x-right anchor-y-middle"
    assert theme.review.qr_position.css_classes == "anchor anchor-x-right anchor-y-top"


def test_theme_file_is_next_to_configuration_file(tmp_path: Path) -> None:
    assert theme_path_for(tmp_path / "config.json") == tmp_path / "theme.json"
    assert theme_path_for(Path("config.json")) == Path("theme.json")


def test_partial_theme_keeps_defaults_for_absent_values() -> None:
    """Older or minimal theme files only override what they declare."""
    theme = parse_theme({"colors": {"primary": "#AA3366"}, "review": {"photo_size": "large"}})

    assert theme.colors == ThemeColors(primary="#AA3366")
    assert theme.background == ThemeSettings().background
    assert theme.preview == PreviewLayout()
    assert theme.review == ReviewLayout(photo_size=HeroSize.LARGE)


@pytest.mark.parametrize(
    "value", ["red", "#fff", "#12345g", "#1234567", "#123456;", "url(x)", ""]
)
def test_invalid_colors_are_rejected(value: str) -> None:
    with pytest.raises(ConfigurationError, match=r"^colors\.surface must be a #rrggbb"):
        parse_theme({"colors": {"surface": value}})


def test_non_string_color_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match=r"^colors\.primary must be a string"):
        parse_theme({"colors": {"primary": 123}})


def test_background_settings_accept_allowlisted_values() -> None:
    theme = parse_theme(
        {
            "background": {
                "image": "A" * 22 + ".jpg",
                "fit": "contain",
                "position": "bottom-right",
            }
        }
    )

    assert theme.background.image == "A" * 22 + ".jpg"
    assert theme.background.fit is BackgroundFit.CONTAIN
    assert theme.background.position is BackgroundPosition.BOTTOM_RIGHT
    assert theme.css_variables()["--booth-background-position"] == "bottom right"
    assert parse_theme({"background": {"image": None}}).background.image is None
    assert parse_theme({"background": {"image": ""}}).background.image is None


@pytest.mark.parametrize(
    ("background", "message"),
    [
        ({"fit": "stretch"}, r"^background\.fit must be one of: cover, contain"),
        ({"position": "50% 50%"}, r"^background\.position must be one of"),
        ({"image": "../config.json"}, r"^background\.image must be a managed"),
        ({"image": "http://example.com/a.jpg"}, r"^background\.image must be a managed"),
        ({"image": 4}, r"^background\.image must be a string or null"),
    ],
)
def test_invalid_background_settings_are_rejected(
    background: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_theme({"background": background})


def test_valid_preview_layout_values() -> None:
    theme = parse_theme(
        {
            "preview": {
                "position": "right",
                "size": "full",
                "fit": "cover",
                "capture_position": "bottom-center",
                "title_visible": False,
                "title_position": "bottom-center",
            }
        }
    )

    assert theme.preview == PreviewLayout(
        position=HeroPosition.RIGHT,
        size=HeroSize.FULL,
        fit=PreviewFit.COVER,
        capture_position=WidgetAnchor.BOTTOM_CENTER,
        title_visible=False,
        title_position=WidgetAnchor.BOTTOM_CENTER,
    )
    assert theme.preview.stage_classes == "hero-right hero-size-full hero-fit-cover"


@pytest.mark.parametrize(
    ("preview", "message"),
    [
        ({"position": "top"}, r"^preview\.position must be one of"),
        ({"size": "huge"}, r"^preview\.size must be one of"),
        ({"fit": "fill"}, r"^preview\.fit must be one of"),
        ({"capture_position": "center"}, r"^preview\.capture_position must be one of"),
        ({"title_visible": "yes"}, r"^preview\.title_visible must be a boolean"),
        (
            {"capture_position": "top-right", "title_position": "top-right"},
            r"^preview\.title_position must differ",
        ),
        ({"x": 10}, r"^unknown preview setting: x"),
    ],
)
def test_invalid_preview_layout_values_are_rejected(
    preview: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_theme({"preview": preview})


def test_valid_review_layout_values() -> None:
    theme = parse_theme(
        {
            "review": {
                "photo_position": "center",
                "photo_size": "small",
                "qr_position": "left",
                "actions_position": "right",
            }
        }
    )

    assert theme.review == ReviewLayout(
        photo_position=HeroPosition.CENTER,
        photo_size=HeroSize.SMALL,
        qr_position=WidgetAnchor.LEFT,
        actions_position=WidgetAnchor.RIGHT,
    )


@pytest.mark.parametrize(
    "positions",
    [
        {"qr_position": "top-right", "actions_position": "top-right"},
        {"qr_position": "right", "actions_position": "bottom-right"},
        {"qr_position": "top-center", "actions_position": "top-left"},
    ],
)
def test_overlapping_review_panels_are_rejected(positions: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError, match=r"^review\.actions_position overlaps"):
        parse_theme({"review": positions})


def test_invalid_review_enum_and_unknown_sections_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match=r"^review\.photo_size must be one of"):
        parse_theme({"review": {"photo_size": 2}})
    with pytest.raises(ConfigurationError, match=r"^unknown theme setting: css"):
        parse_theme({"css": "body{}"})
    with pytest.raises(ConfigurationError, match=r"^colors must be an object"):
        parse_theme({"colors": "#000000"})


def test_theme_persistence_round_trips_atomically(tmp_path: Path) -> None:
    path = tmp_path / "theme.json"
    theme = parse_theme(
        {
            "colors": {"background": "#000000"},
            "preview": {"position": "center", "title_visible": False},
            "review": {"qr_position": "bottom-left", "actions_position": "bottom-right"},
        }
    )

    save_theme(path, theme)

    assert load_theme(path) == theme
    assert json.loads(path.read_text(encoding="utf-8"))["preview"]["position"] == "center"
    assert not list(tmp_path.glob(".*.tmp"))


def test_malformed_theme_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "theme.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="cannot read configuration file"):
        load_theme(path)


@pytest.mark.parametrize("name", ["default.json", "artwork.json", "alternate-review.json"])
def test_documented_example_themes_are_valid(name: str) -> None:
    """The three acceptance-criteria themes in docs/themes load unchanged."""
    path = Path(__file__).resolve().parents[1] / "docs" / "themes" / name

    assert isinstance(load_theme(path), ThemeSettings)


def test_background_service_normalizes_valid_uploads(tmp_path: Path) -> None:
    """Uploads get controlled names; transparency selects PNG, otherwise JPEG."""
    service = BackgroundService(tmp_path)

    opaque = service.store(_image_bytes("RGB", "PNG"))
    transparent = service.store(_image_bytes("RGBA", "PNG"))

    assert opaque.endswith(".jpg") and len(opaque) == 26
    assert transparent.endswith(".png")
    assert service.exists(opaque) and service.exists(transparent)
    assert service.read(opaque).mimetype == "image/jpeg"
    with Image.open(BytesIO(service.read(transparent).data)) as stored:
        assert stored.format == "PNG"
    assert {image.identifier for image in service.list_backgrounds()} == {opaque, transparent}
    assert not service.exists("../" + opaque)


@pytest.mark.parametrize(
    "data",
    [b"not an image", b"", b"GIF89a" + b"\x00" * 20],
)
def test_background_service_rejects_non_images(tmp_path: Path, data: bytes) -> None:
    service = BackgroundService(tmp_path)

    with pytest.raises(InvalidBackgroundError):
        service.store(data)

    assert service.list_backgrounds() == ()


def test_background_service_rejects_unsupported_formats(tmp_path: Path) -> None:
    with pytest.raises(InvalidBackgroundError):
        BackgroundService(tmp_path).store(_image_bytes("RGB", "GIF"))


def test_participant_pages_receive_validated_theme(tmp_path: Path) -> None:
    """Booth and review render theme variables and layout classes from the model."""
    theme = parse_theme(
        {
            "colors": {"primary": "#123abc"},
            "preview": {"position": "right", "size": "small", "capture_position": "bottom-left"},
            "review": {"qr_position": "top-left", "actions_position": "bottom-left"},
        }
    )
    app = _app(tmp_path, theme=theme, public_base_url="http://192.168.1.42:5000")
    client = app.test_client()

    booth = client.get("/").get_data(as_text=True)

    assert "--booth-primary-color: #123abc;" in booth
    assert 'class="stage hero-right hero-size-small hero-fit-contain"' in booth
    assert 'class="anchor anchor-x-left anchor-y-bottom"' in booth
    assert "participant.css" in booth
    assert "--booth-background-image" not in booth

    review = client.get(_capture_review_url(client)).get_data(as_text=True)

    assert "--booth-primary-color: #123abc;" in review
    assert 'class="stage hero-left hero-size-medium hero-fit-contain"' in review
    assert "--hero-aspect: 1.3333" in review
    assert 'class="anchor anchor-x-left anchor-y-top"' in review
    assert "data:image/png;base64," in review
    assert "Connectez-vous au réseau Wi-Fi du photobooth" in review
    assert client.get("/static/participant.css").status_code == 200
    _close(app)


def test_hidden_title_is_kept_for_accessibility_only(tmp_path: Path) -> None:
    app = _app(tmp_path, theme=parse_theme({"preview": {"title_visible": False}}))

    booth = app.test_client().get("/").get_data(as_text=True)

    assert '<h1 class="visually-hidden">Photobooth</h1>' in booth
    assert "booth-title" not in booth
    _close(app)


def test_configured_background_is_served_and_missing_file_falls_back(tmp_path: Path) -> None:
    """A deleted managed image leaves the solid background color in use."""
    identifier = BackgroundService(tmp_path / "data").store(_image_bytes("RGB", "PNG"))
    theme = parse_theme({"background": {"image": identifier, "fit": "contain"}})
    app = _app(tmp_path, theme=theme)
    client = app.test_client()

    booth = client.get("/").get_data(as_text=True)
    assert f'--booth-background-image: url("/media/backgrounds/{identifier}");' in booth
    assert "has-background-image" in booth
    assert "--booth-background-fit: contain;" in booth
    image = client.get(f"/media/backgrounds/{identifier}")
    assert image.status_code == 200
    assert image.mimetype == "image/jpeg"
    assert client.get("/media/backgrounds/..%2Fconfig.json").status_code == 404

    (tmp_path / "data" / "backgrounds" / identifier).unlink()

    fallback = client.get("/").get_data(as_text=True)
    assert "--booth-background-image" not in fallback
    assert "has-background-image" not in fallback
    assert client.get(f"/media/backgrounds/{identifier}").status_code == 404
    _close(app)


def test_admin_renders_current_appearance(tmp_path: Path) -> None:
    app = _app(tmp_path)
    page = app.test_client().get("/admin", headers=_auth()).get_data(as_text=True)

    assert "Event appearance" in page
    assert 'name="theme_colors_primary" type="color" value="#f2b544"' in page
    assert '<option value="top-right" selected>Top right</option>' in page
    assert 'enctype="multipart/form-data"' in page
    _close(app)


def test_admin_theme_update_persists_and_applies_immediately(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/admin/theme",
        data=_theme_form(
            theme_colors_primary="#ff4f8b",
            theme_preview_position="center",
            theme_preview_capture_position="bottom-center",
            theme_review_qr_position="left",
            theme_review_actions_position="right",
        ),
        headers=_auth(),
    )

    assert response.status_code == 303
    assert "saved=theme" in response.headers["Location"]
    stored = load_theme(tmp_path / "theme.json")
    assert stored.colors.primary == "#ff4f8b"
    assert stored.review.qr_position is WidgetAnchor.LEFT
    assert cast(ThemeSettings, app.extensions["photobooth.theme"]) == stored
    booth = client.get("/").get_data(as_text=True)
    assert "--booth-primary-color: #ff4f8b;" in booth
    assert "hero-center" in booth
    page = client.get(response.headers["Location"], headers=_auth())
    assert b"Appearance was saved" in page.data
    _close(app)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("theme_colors_background", "red; background: url(x)"),
        ("theme_background_position", "10px 20px"),
        ("theme_preview_size", "huge"),
        ("theme_review_actions_position", "top-right"),
        ("theme_background_image", "A" * 22 + ".jpg"),
    ],
)
def test_admin_rejects_invalid_theme_values_without_persistence(
    tmp_path: Path, field: str, value: str
) -> None:
    """Invalid colors, enums, overlaps and unknown backgrounds keep the prior theme."""
    app = _app(tmp_path)
    client = app.test_client()

    response = client.post("/admin/theme", data=_theme_form(**{field: value}), headers=_auth())

    assert response.status_code == 400
    assert b'class="error"' in response.data
    assert not (tmp_path / "theme.json").exists()
    assert app.extensions["photobooth.theme"] == ThemeSettings()
    _close(app)


def test_admin_upload_stores_and_selects_background(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()
    form: dict[str, object] = dict(_theme_form())
    form["theme_background_upload"] = (BytesIO(_image_bytes("RGB", "JPEG")), "../../evil.jpg")

    response = client.post(
        "/admin/theme", data=form, headers=_auth(), content_type="multipart/form-data"
    )

    assert response.status_code == 303
    identifier = load_theme(tmp_path / "theme.json").background.image
    assert identifier is not None and "evil" not in identifier
    assert (tmp_path / "data" / "backgrounds" / identifier).is_file()
    assert not (tmp_path / "evil.jpg").exists()
    page = client.get("/admin", headers=_auth()).get_data(as_text=True)
    assert f'<option value="{identifier}" selected>' in page
    _close(app)


def test_admin_rejects_non_image_upload(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()
    form: dict[str, object] = dict(_theme_form())
    form["theme_background_upload"] = (BytesIO(b"<script>alert(1)</script>"), "image.png")

    response = client.post(
        "/admin/theme", data=form, headers=_auth(), content_type="multipart/form-data"
    )

    assert response.status_code == 400
    assert b"not a supported JPEG, PNG or WebP image" in response.data
    assert not (tmp_path / "theme.json").exists()
    assert not (tmp_path / "data" / "backgrounds").exists() or not any(
        (tmp_path / "data" / "backgrounds").iterdir()
    )
    _close(app)


def test_theme_update_requires_admin_authentication(tmp_path: Path) -> None:
    app = _app(tmp_path)

    response = app.test_client().post("/admin/theme", data=_theme_form())

    assert response.status_code == 401
    assert not (tmp_path / "theme.json").exists()
    _close(app)


def test_booth_settings_save_keeps_active_theme(tmp_path: Path) -> None:
    """The existing settings form neither persists nor resets the event theme."""
    theme = parse_theme({"colors": {"primary": "#00ff00"}})
    app = _app(tmp_path, theme=theme)
    client = app.test_client()
    form = {
        "booth_name": "Photobooth",
        "wifi_network_name": "Fête",
        "countdown_seconds": "3",
        "idle_timeout_seconds": "120",
        "slideshow_interval_seconds": "5",
        "slideshow_enabled": "true",
        "public_base_url": "",
        "download_token_lifetime_seconds": "3600",
        "camera_backend": "synthetic",
    }

    assert client.post("/admin/settings", data=form, headers=_auth()).status_code == 303

    assert app.extensions["photobooth.theme"] == theme
    assert "theme" not in json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    _close(app)


def _app(
    tmp_path: Path,
    theme: ThemeSettings | None = None,
    public_base_url: str | None = None,
) -> Flask:
    """Build an isolated app whose theme file lives in ``tmp_path``."""
    configuration = ApplicationConfig(
        startup=StartupConfig(
            data_root=tmp_path / "data",
            admin_secret=_SECRET,
            public_base_url=public_base_url,
        ),
        booth=BoothSettings(countdown_seconds=0),
        config_path=tmp_path / "config.json",
    )
    return create_app(configuration, SyntheticCameraBackend(), theme=theme)


def _auth() -> dict[str, str]:
    """Return Basic credentials for the fixed admin user."""
    credential = base64.b64encode(f"admin:{_SECRET}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {credential}"}


def _theme_form(**overrides: str) -> dict[str, str]:
    """Return a complete default appearance submission with selected overrides."""
    values = {
        "theme_colors_background": "#111316",
        "theme_colors_surface": "#1f2328",
        "theme_colors_foreground": "#f5f1e8",
        "theme_colors_primary": "#f2b544",
        "theme_colors_primary_text": "#15171a",
        "theme_background_image": "",
        "theme_background_fit": "cover",
        "theme_background_position": "center",
        "theme_preview_position": "left",
        "theme_preview_size": "large",
        "theme_preview_fit": "contain",
        "theme_preview_capture_position": "right",
        "theme_preview_title_visible": "true",
        "theme_preview_title_position": "top-right",
        "theme_review_photo_position": "left",
        "theme_review_photo_size": "medium",
        "theme_review_qr_position": "top-right",
        "theme_review_actions_position": "bottom-right",
    }
    values.update(overrides)
    return values


def _image_bytes(mode: str, image_format: str) -> bytes:
    """Encode a small generated image in the requested mode and format."""
    buffer = BytesIO()
    Image.new(mode, (64, 36), color=(20, 120, 200, 128)[: len(mode)]).save(
        buffer, format=image_format
    )
    return buffer.getvalue()


def _capture_review_url(client: FlaskClient) -> str:
    """Capture one synthetic photo and return its review URL."""
    payload = client.post("/capture").get_json()
    assert isinstance(payload, dict)
    return cast(str, cast(dict[str, object], payload)["review_url"])


def _close(app: Flask) -> None:
    """Release the application-owned preview service."""
    cast(PreviewService, app.extensions["photobooth.preview"]).close()
