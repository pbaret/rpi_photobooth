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
from photobooth.camera import (
	CameraBackend,
	CameraSettingCapability,
	CameraSettingType,
	CameraSettingValue,
	ValidatedCameraSetting,
	validate_camera_setting,
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
	camera = cast(CameraBackend, current_app.extensions["photobooth.camera"])
	camera_capabilities = camera.get_capabilities()
	camera_updates: list[ValidatedCameraSetting] = []
	try:
		updated_camera_settings, camera_updates = _camera_setting_updates(
			raw_values, persisted.startup.camera_settings, camera_capabilities
		)
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
			camera_settings=updated_camera_settings,
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
		return _render_admin(
			values,
			errors,
			status=400,
			camera_values=_camera_form_values(raw_values),
		)

	try:
		save_configuration(updated)
	except OSError:
		return _render_admin(
			values,
			{"form": "Settings could not be saved. The previous configuration remains active."},
			status=500,
			camera_values=_camera_form_values(raw_values),
		)

	active_camera_settings = dict(effective.startup.camera_settings)
	capability_by_id = {item.identifier: item for item in camera_capabilities}
	for setting in camera_updates:
		capability = capability_by_id[setting.identifier]
		if capability.restart_required:
			if camera_backend is effective.startup.camera_backend:
				camera.configure_settings({setting.identifier: setting.value})
		else:
			applied_value = camera.apply_setting(setting)
			active_camera_settings[setting.identifier] = applied_value
	current_app.extensions["photobooth.persisted_configuration"] = updated
	effective_startup = replace(
		updated.startup,
		camera_backend=effective.startup.camera_backend,
		camera_settings=active_camera_settings,
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
	camera_values: dict[str, str] | None = None,
) -> ResponseReturnValue:
	"""Render one admin response without exposing deployment or filesystem data."""
	persisted = _persisted_configuration()
	effective = _effective_configuration()
	gallery = cast(GalleryService, current_app.extensions["photobooth.gallery"])
	printer = cast(PrinterBackend, current_app.extensions["photobooth.printer"])
	camera = cast(CameraBackend, current_app.extensions["photobooth.camera"])
	camera_capabilities = camera.get_capabilities()
	persisted_camera_settings = persisted.startup.camera_settings
	camera_controls = tuple(
		replace(
			capability,
			requested_value=persisted_camera_settings.get(
				capability.identifier, capability.requested_value
			),
		)
		for capability in camera_capabilities
	)
	camera_restart_required = any(
		capability.restart_required
		and persisted_camera_settings.get(
			capability.identifier, capability.requested_value
		)
		!= capability.effective_value
		for capability in camera_controls
	)
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
		camera_restart_required=camera_restart_required,
		camera_capabilities=camera_controls,
		camera_values=camera_values or {},
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
	if message.startswith("camera setting "):
		identifier = message.removeprefix("camera setting ").split(maxsplit=1)[0]
		return f"camera_setting_{identifier}"
	for field in fields:
		if message.startswith(field):
			return field
	return "form"


def _camera_setting_updates(
	raw_values: dict[str, str],
	current_settings: dict[str, CameraSettingValue],
	capabilities: tuple[CameraSettingCapability, ...],
) -> tuple[dict[str, CameraSettingValue], list[ValidatedCameraSetting]]:
	"""Validate active-backend submissions and retain unknown saved requests.

	Only declared capabilities can be updated. Previously saved unsupported
	keys are copied unchanged so changing the active backend does not erase them.
	"""
	prefix = "camera_setting_"
	submitted = {key[len(prefix):] for key in raw_values if key.startswith(prefix)}
	capability_by_id = {item.identifier: item for item in capabilities}
	unknown = submitted - capability_by_id.keys()
	if unknown:
		identifier = sorted(unknown)[0]
		raise ConfigurationError(f"camera setting {identifier} is unsupported")

	updated = dict(current_settings)
	validated_settings: list[ValidatedCameraSetting] = []
	form_was_submitted = raw_values.get("camera_settings_present") == "true"
	for capability in capabilities:
		field_name = f"{prefix}{capability.identifier}"
		is_submitted = capability.identifier in submitted
		if capability.read_only:
			if is_submitted:
				raise ConfigurationError(f"camera setting {capability.identifier} is read-only")
			continue
		if not is_submitted and not (
			form_was_submitted and capability.value_type is CameraSettingType.BOOLEAN
		):
			continue
		raw_value = raw_values.get(field_name, "false")
		try:
			value = _camera_form_value(capability, raw_value)
			validated = validate_camera_setting(capability, value)
		except ValueError as error:
			raise ConfigurationError(
				f"camera setting {capability.identifier} {error}"
			) from error
		updated[capability.identifier] = validated.value
		validated_settings.append(validated)
	return updated, validated_settings


def _camera_form_value(
	capability: CameraSettingCapability, raw_value: str
) -> CameraSettingValue:
	"""Parse a submitted native control value before capability validation."""
	if capability.value_type is CameraSettingType.BOOLEAN:
		if raw_value not in {"true", "false"}:
			raise ValueError("must be true or false")
		return raw_value == "true"
	if capability.value_type is CameraSettingType.INTEGER:
		return int(raw_value)
	if capability.value_type is CameraSettingType.FLOAT:
		return float(raw_value)
	return raw_value


def _camera_form_values(raw_values: dict[str, str]) -> dict[str, str]:
	"""Retain submitted camera control text for a validation-error response."""
	prefix = "camera_setting_"
	return {
		key[len(prefix):]: value
		for key, value in raw_values.items()
		if key.startswith(prefix)
	}