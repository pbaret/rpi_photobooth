"""Flask application construction and route registration."""

from flask import Flask

from photobooth.camera import CameraBackend, OpenCVCameraBackend, SyntheticCameraBackend
from photobooth.config import (
    ApplicationConfig,
    CameraBackend as CameraBackendKind,
    load_configuration,
)
from photobooth.printing import NullPrinterBackend, PrinterBackend
from photobooth.routes.admin import admin_blueprint
from photobooth.routes.booth import booth_blueprint
from photobooth.routes.downloads import downloads_blueprint
from photobooth.routes.media import media_blueprint
from photobooth.services.downloads import DownloadService
from photobooth.services.preview import PreviewService
from photobooth.services.gallery import GalleryService


def create_app(
    configuration: ApplicationConfig | None = None,
    camera_backend: CameraBackend | None = None,
    gallery_service: GalleryService | None = None,
    printer_backend: PrinterBackend | None = None,
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
    active_camera.configure_settings(active_configuration.startup.camera_settings)
    active_gallery = (
        gallery_service
        if gallery_service is not None
        else GalleryService(active_configuration.startup.data_root)
    )
    active_printer = printer_backend if printer_backend is not None else NullPrinterBackend()
    app = Flask(__name__)
    app.config["DEBUG"] = active_configuration.startup.debug
    app.extensions["photobooth.configuration"] = active_configuration
    app.extensions["photobooth.persisted_configuration"] = active_configuration
    app.extensions["photobooth.camera"] = active_camera
    app.extensions["photobooth.gallery"] = active_gallery
    app.extensions["photobooth.downloads"] = DownloadService(
        active_configuration.startup.data_root,
        active_gallery,
        active_configuration.startup.download_token_lifetime_seconds,
    )
    app.extensions["photobooth.printer"] = active_printer
    app.extensions["photobooth.preview"] = PreviewService(active_camera, active_gallery)
    app.register_blueprint(booth_blueprint)
    app.register_blueprint(downloads_blueprint)
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