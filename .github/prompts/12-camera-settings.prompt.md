---
agent: agent
description: Make camera settings capability-driven across backends and admin
---

# Goal

Implement a capability-driven camera settings system and integrate it into the
existing administration interface.

At the end of this milestone:

1. each camera backend declares the controls it actually supports;
2. the admin Camera section is generated from those declared capabilities;
3. unsupported controls are not presented as available;
4. submitted values are validated against backend capabilities;
5. the application distinguishes requested, validated and effectively applied
   values;
6. the UI indicates when a setting requires a camera restart;
7. adding future controls to RpicamCameraBackend must not require rewriting the
   administration UI.

Do not implement RpicamCameraBackend in this milestone.

# Context

The application already provides:

- CameraBackend;
- SyntheticCameraBackend;
- OpenCVCameraBackend;
- typed camera settings;
- persistent configuration;
- an administration interface.

The future Raspberry Pi backend will expose additional Camera Module 3 controls,
but those controls must not be hard-coded into the admin UI before the backend
exists and can declare them.

The purpose of this milestone is to establish the generic capability model that
future camera backends will use.

# Sources

Before editing, inspect only the relevant:

- CameraBackend contract;
- CameraSettings and existing camera domain models;
- SyntheticCameraBackend;
- OpenCVCameraBackend;
- camera configuration;
- admin Camera section;
- `docs/architecture.md`;
- `docs/configuration.md`;
- applicable repository instructions.

Extend existing types rather than creating a parallel camera-settings model.

# Capability model

Create or complete the typed domain model representing a camera control
capability.

A capability must be able to describe, where applicable:

- stable setting identifier;
- user-facing label or description;
- value type;
- current/effective value when known;
- configured/requested value when relevant;
- default value;
- allowed discrete values for enum-like controls;
- minimum value;
- maximum value;
- step where meaningful;
- read-only status;
- whether changing the value requires camera restart.

Do not force every field onto every capability when it does not semantically
apply.

Prefer a simple, type-safe representation over a generic
`dict[str, Any]`.

# Setting lifecycle

Make the following concepts explicit and keep them distinct:

## Requested

The value requested through configuration or administration.

## Capability

What the active backend declares that it can support.

## Validated

A requested value that has passed validation against the declared capability.

## Effective

The value actually applied or reported by the active backend.

## Unsupported

A configured setting for which the current backend does not declare a
capability.

Do not report a requested value as effective merely because it was persisted.

# CameraBackend integration

CameraBackend must provide the application with the capabilities of the active
backend through the existing contract or the smallest coherent extension of it.

Each concrete backend remains responsible for declaring its own capabilities.

Do not make the admin layer inspect backend implementation types such as:

- `isinstance(..., OpenCVCameraBackend)`;
- backend-name conditionals;
- future rpicam-specific conditionals.

The admin layer consumes CameraBackend capabilities only.

# SyntheticCameraBackend

Give SyntheticCameraBackend a small but representative set of capabilities
useful for testing the complete capability model.

Include enough variety to exercise, for example:

- boolean control;
- bounded numeric control;
- enum-like control;
- read-only control;
- restart-required control.

These controls are synthetic test capabilities.

Do not present them as real camera hardware capabilities.

# OpenCVCameraBackend

Inspect the controls currently implemented by OpenCVCameraBackend.

Declare only controls that the backend can actually support through its
existing implementation.

Do not add speculative OpenCV controls solely to populate the administration
screen.

If OpenCV cannot reliably report or apply a generic camera control across the
current implementation, do not advertise that control as supported.

Keep requested and effective resolution distinct if the backend already
observes that distinction.

# Future Rpicam support

Do not implement RpicamCameraBackend.

Do not hard-code Camera Module 3 capabilities.

The model should nevertheless be able to represent future controls such as:

- autofocus mode;
- manual lens position;
- exposure time;
- analogue gain;
- exposure compensation;
- white balance;
- colour gains;
- brightness;
- contrast;
- saturation;
- sharpness;
- denoise;
- flicker control.

This list validates the expressiveness of the domain model only.

Do not create fake capabilities for these controls.

# Admin integration

Update the existing Admin > Camera section so that configurable camera controls
are rendered from the capabilities reported by the active backend.

Use appropriate native HTML controls based on capability type.

Examples:

- boolean -> checkbox;
- discrete enum -> select;
- bounded integer/float -> numeric input;
- read-only -> non-editable displayed value.

Do not create a large hard-coded list of backend-specific form fields.

For each relevant setting, make it possible to distinguish:

- configured/requested value;
- effective value, when known;
- restart-required status.

Unsupported settings must not appear as usable controls.

If a setting remains in persisted configuration but is unsupported by the
currently selected backend, do not silently delete it.

# Applying settings

When the administrator submits camera settings:

1. resolve the active backend capabilities;
2. validate submitted values against those capabilities;
3. reject invalid values server-side;
4. persist valid requested values using the existing configuration mechanism;
5. apply immediately only when the backend contract supports doing so safely;
6. otherwise mark the setting as requiring restart.

Do not restart the camera implicitly unless the existing lifecycle already
provides a safe explicit mechanism for doing so.

Do not claim that a value is effective unless the backend applied or reported
it.

# Backend switching

If the current application already allows camera backend selection:

- changing backend must not cause unsupported settings to be treated as valid;
- backend-specific settings may remain persisted for future reuse;
- only capabilities of the currently active backend are presented as
  currently usable.

Do not redesign backend switching if it is not already supported.

# Toolchain

Do not add a dependency.

Use typed domain models and standard-library typing constructs.

Do not introduce:

- a schema framework;
- frontend framework;
- OpenCV-specific types into the domain model;
- rpicam-specific types into the domain model.

# Documentation

Follow repository-wide typing and documentation requirements.

In particular document:

- capability ownership;
- requested versus effective values;
- validation behavior;
- unsupported-setting behavior;
- read-only controls;
- restart-required semantics;
- how concrete backends declare capabilities.

The documentation must make clear that a capability is a backend declaration,
not a guarantee derived from the configuration model.

# Tests

Add or update pytest tests covering at least:

- representative SyntheticCameraBackend capabilities;
- capability value types;
- bounded numeric validation;
- enum validation;
- boolean controls;
- read-only controls;
- restart-required controls;
- requested versus effective value distinction;
- unsupported settings;
- preservation of an unsupported persisted setting;
- admin rendering based on capabilities;
- invalid admin value rejected server-side;
- backend exposing only a subset of possible controls.

Use SyntheticCameraBackend and typed fakes where appropriate.

Do not require physical camera hardware.

# Validation

Execute:

`uv run pyright`

and the relevant pytest tests.

Run the complete pytest suite because this milestone changes CameraBackend,
configuration and administration behavior.

# Manual validation

Provide a concise manual validation procedure using the currently available
backends:

1. start with SyntheticCameraBackend;
2. open Admin > Camera;
3. verify only declared synthetic capabilities appear;
4. verify the appropriate HTML controls are used;
5. change a writable value and save;
6. verify requested/effective status;
7. verify read-only and restart-required controls behave correctly;
8. start with OpenCVCameraBackend;
9. verify the admin now exposes only capabilities declared by OpenCV;
10. verify no future rpicam controls are presented as supported.

# Expected result

Before editing:

1. inspect the existing camera settings, capabilities and admin implementation;
2. identify any capability model already present;
3. identify which OpenCV controls are actually supported today;
4. propose the smallest necessary model extension;
5. list files expected to change.

After implementation report only:

- files changed;
- capability model introduced or extended;
- Synthetic capabilities declared;
- OpenCV capabilities declared;
- admin behavior changed;
- Pyright result;
- pytest result;
- controls deliberately deferred to RpicamCameraBackend.

Stop after this milestone.

Do not implement:

- RpicamCameraBackend;
- Picamera2;
- Camera Module 3-specific behavior;
- CUPS;
- final visual branding.