"""Behavioral tests for the initial Flask application."""

from flask.testing import FlaskClient

from photobooth.app import create_app


def test_booth_homepage_renders() -> None:
    """The application factory exposes a rendered booth page without hardware."""
    app = create_app()
    client: FlaskClient = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Photobooth" in response.data
    assert b"ready to be configured" in response.data