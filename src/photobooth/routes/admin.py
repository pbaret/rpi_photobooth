"""Protect and operate the trusted-local-network administration interface.

The deployment-owned administrator secret is checked with HTTP Basic
authentication and constant-time comparison. This is a lightweight boundary
for normal booth users, not Internet-facing authentication; deployments must
provide transport security when credentials cross an untrusted network.
"""

from dataclasses import replace
import hmac

from flask import Blueprint, Response, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from typing import cast

from photobooth.config import (
	ApplicationConfig,
	BoothSettings,
	CameraBackend as CameraBackendKind,
	ConfigurationError,
	save_configuration,
)
from photobooth.printing import PrinterBackend
from photobooth.services.downloads import DownloadService
from photobooth.services.gallery import GalleryError, GalleryService

admin_blueprint = Blueprint("admin", __name__, url_prefix="/admin")


@admin_blueprint.before_request
def require_admin_secret() -> Response | None:
	"""Reject missing or invalid Basic credentials before admin handlers run."""
	configuration = _persisted_configuration()
	secret = configuration.startup.admin_secret
	if secret is None or not secret:
		return Response("Administration is not configured", status=503)
	authorization = request.authorization
	if (
		authorization is None
		or authorization.type.lower() != "basic"
		or authorization.username != "admin"
		or authorization.password is None
		or not hmac.compare_digest(
			authorization.password.encode("utf-8"), secret.encode("utf-8")
		)
	):
		return Response(
			"Authentication required",
			status=401,
			headers={
				"WWW-Authenticate": 'Basic realm="Photobooth administration", charset="UTF-8"'
			},
		)
	return None


@admin_blueprint.get("")
def administration() -> ResponseReturnValue:
	"""Render persisted and effective settings with safe operational diagnostics."""
	return _render_admin()


@admin_blueprint.post("/settings")
def update_settings() -> ResponseReturnValue:
	"""Validate, atomically persist, and selectively apply submitted settings."""
	persisted = _persisted_configuration()
	effective = _effective_configuration()
	raw_values = request.form.to_dict(flat=True)
	values = _submitted_values(raw_values, persisted)
	try:
		backend_value = raw_values.get(
			"camera_backend", persisted.startup.camera_backend.value
		)
		try:
			camera_backend = CameraBackendKind(backend_value)
		except ValueError as error:
			raise ConfigurationError(
				"camera_backend must be a supported camera backend"
			) from error
		if (
			camera_backend is CameraBackendKind.RPICAM
			and persisted.startup.camera_backend is not CameraBackendKind.RPICAM
		):
			raise ConfigurationError("camera_backend rpicam is not implemented yet")

		startup = replace(
			persisted.startup,
			camera_backend=camera_backend,
			public_base_url=_optional_form_value(raw_values, "public_base_url"),
			download_token_lifetime_seconds=_integer_form_value(
				raw_values, "download_token_lifetime_seconds"
			),
		)
		booth = BoothSettings(
			booth_name=raw_values.get("booth_name", ""),
			countdown_seconds=_integer_form_value(raw_values, "countdown_seconds"),
			idle_timeout_seconds=_integer_form_value(raw_values, "idle_timeout_seconds"),
			slideshow_enabled=raw_values.get("slideshow_enabled") == "true",
			slideshow_interval_seconds=_integer_form_value(
				raw_values, "slideshow_interval_seconds"
			),
		)
		updated = ApplicationConfig(startup, booth, persisted.config_path)
	except (ConfigurationError, ValueError) as error:
		field = _error_field(str(error))
		errors = {field: str(error)}
		return _render_admin(values, errors, status=400)

	try:
		save_configuration(updated)
	except OSError:
		return _render_admin(
			values,
			{"form": "Settings could not be saved. The previous configuration remains active."},
			status=500,
		)

	current_app.extensions["photobooth.persisted_configuration"] = updated
	effective_startup = replace(
		updated.startup,
		camera_backend=effective.startup.camera_backend,
	)
	active = ApplicationConfig(effective_startup, updated.booth, updated.config_path)
	current_app.extensions["photobooth.configuration"] = active
	gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
	current_app.extensions["photobooth.downloads"] = DownloadService(
		active.startup.data_root,
		gallery,
		active.startup.download_token_lifetime_seconds,
	)
	return redirect(url_for("admin.administration", saved="1"), code=303)


def _render_admin(
	values: dict[str, str | bool] | None = None,
	errors: dict[str, str] | None = None,
	status: int = 200,
) -> ResponseReturnValue:
	"""Render one admin response without exposing deployment or filesystem data."""
	persisted = _persisted_configuration()
	effective = _effective_configuration()
	gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
	printer = cast(PrinterBackend, current_app.extensions["photobooth.printer"])
	try:
		photo_count: int | None = len(gallery.list_photos())
	except GalleryError:
		photo_count = None
	rendered = render_template(
		"admin/index.html",
		values=values if values is not None else _submitted_values({}, persisted),
		errors=errors or {},
		saved=request.args.get("saved") == "1",
		persisted=persisted,
		effective=effective,
		restart_required=(
			persisted.startup.camera_backend is not effective.startup.camera_backend
		),
		photo_count=photo_count,
		printer_name=type(printer).__name__,
	)
	return rendered if status == 200 else (rendered, status)


def _persisted_configuration() -> ApplicationConfig:
	"""Return the latest validated configuration intended for disk."""
	return cast(
		ApplicationConfig,
		current_app.extensions["photobooth.persisted_configuration"],
	)


def _effective_configuration() -> ApplicationConfig:
	"""Return settings currently consumed by request-time application behavior."""
	return cast(ApplicationConfig, current_app.extensions["photobooth.configuration"])


def _submitted_values(
	raw_values: dict[str, str], configuration: ApplicationConfig
) -> dict[str, str | bool]:
	"""Build safe form values, retaining user text without reflecting secrets."""
	return {
		"booth_name": raw_values.get("booth_name", configuration.booth.booth_name),
		"countdown_seconds": raw_values.get(
			"countdown_seconds", str(configuration.booth.countdown_seconds)
		),
		"idle_timeout_seconds": raw_values.get(
			"idle_timeout_seconds", str(configuration.booth.idle_timeout_seconds)
		),
		"slideshow_enabled": (
			raw_values.get("slideshow_enabled") == "true"
			if "slideshow_enabled" in raw_values
			else configuration.booth.slideshow_enabled
		),
		"slideshow_interval_seconds": raw_values.get(
			"slideshow_interval_seconds",
			str(configuration.booth.slideshow_interval_seconds),
		),
		"public_base_url": raw_values.get(
			"public_base_url", configuration.startup.public_base_url or ""
		),
		"download_token_lifetime_seconds": raw_values.get(
			"download_token_lifetime_seconds",
			str(configuration.startup.download_token_lifetime_seconds),
		),
		"camera_backend": raw_values.get(
			"camera_backend", configuration.startup.camera_backend.value
		),
	}


def _integer_form_value(values: dict[str, str], name: str) -> int:
	"""Parse a submitted integer and leave bounds enforcement to config models."""
	raw_value = values.get(name, "")
	try:
		return int(raw_value)
	except ValueError as error:
		raise ConfigurationError(f"{name} must be an integer") from error


def _optional_form_value(values: dict[str, str], name: str) -> str | None:
	"""Map a blank optional URL input to None while preserving nonblank input."""
	value = values.get(name, "")
	return value if value else None


def _error_field(message: str) -> str:
	"""Map model validation messages to the matching visible form control."""
	fields = {
		"booth_name",
		"countdown_seconds",
		"idle_timeout_seconds",
		"slideshow_interval_seconds",
		"public_base_url",
		"download_token_lifetime_seconds",
		"camera_backend",
	}
	for field in fields:
		if message.startswith(field):
			return field
	return "form"