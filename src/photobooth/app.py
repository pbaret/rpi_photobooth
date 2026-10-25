"""Flask application construction and route registration."""

from flask import Flask

from photobooth.camera import CameraBackend, OpenCVCameraBackend, SyntheticCameraBackend
from photobooth.config import (
    ApplicationConfig,
    CameraBackend as CameraBackendKind,
    load_configuration,
)
from photobooth.routes.admin import admin_blueprint
from photobooth.routes.booth import booth_blueprint
from photobooth.routes.media import media_blueprint
from photobooth.services.preview import PreviewService


def create_app(
    configuration: ApplicationConfig | None = None,
    camera_backend: CameraBackend | None = None,
) -> Flask:
    """Build the Flask app, select its camera, and register its HTTP adapters.

    The app owns one PreviewService and one camera backend. Tests may inject a
    backend; otherwise startup configuration selects the implementation.
    """
    active_configuration = (
        configuration if configuration is not None else load_configuration()
    )
    active_camera = (
        camera_backend
        if camera_backend is not None
        else _create_camera_backend(active_configuration.startup.camera_backend)
    )
    app = Flask(__name__)
    app.config["DEBUG"] = active_configuration.startup.debug
    app.extensions["photobooth.configuration"] = active_configuration
    app.extensions["photobooth.preview"] = PreviewService(active_camera)
    app.register_blueprint(booth_blueprint)
    app.register_blueprint(media_blueprint)
    app.register_blueprint(admin_blueprint)
    return app


def _create_camera_backend(kind: CameraBackendKind) -> CameraBackend:
    """Construct a supported backend without acquiring hardware at import."""
    if kind is CameraBackendKind.SYNTHETIC:
        return SyntheticCameraBackend()
    if kind is CameraBackendKind.OPENCV:
        return OpenCVCameraBackend()
    raise ValueError(f"camera backend is not implemented: {kind.value}")