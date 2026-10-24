"""Flask application construction and route registration."""

from flask import Flask

from photobooth.config import ApplicationConfig, load_configuration
from photobooth.routes.admin import admin_blueprint
from photobooth.routes.booth import booth_blueprint
from photobooth.routes.media import media_blueprint


def create_app(configuration: ApplicationConfig | None = None) -> Flask:
    """Build the Flask application and register its HTTP adapters."""
    active_configuration = (
        configuration if configuration is not None else load_configuration()
    )
    app = Flask(__name__)
    app.config["DEBUG"] = active_configuration.startup.debug
    app.extensions["photobooth.configuration"] = active_configuration
    app.register_blueprint(booth_blueprint)
    app.register_blueprint(media_blueprint)
    app.register_blueprint(admin_blueprint)
    return app