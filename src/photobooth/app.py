"""Flask application construction and route registration."""

from flask import Flask

from photobooth.routes.admin import admin_blueprint
from photobooth.routes.booth import booth_blueprint
from photobooth.routes.media import media_blueprint


def create_app() -> Flask:
    """Build the Flask application and register its HTTP adapters."""
    app = Flask(__name__)
    app.register_blueprint(booth_blueprint)
    app.register_blueprint(media_blueprint)
    app.register_blueprint(admin_blueprint)
    return app