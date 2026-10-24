---
agent: agent
description: Validate and complete the photobooth architecture before implementation
---

# Goal

Review, validate and complete the initial architecture documentation for the
photobooth before application code is implemented.

This is an architecture-only milestone.

Do not implement application code.

The purpose of this task is not to redesign the project from scratch.
The repository already contains intentional architecture decisions.

Challenge an existing decision only when a concrete technical problem,
contradiction or unnecessary complexity is identified.

# Context

The project is a local touch-first photobooth.

Development platform:

- regular laptop or desktop computer;
- Python;
- Flask;
- uv;
- webcam accessed through OpenCV;
- SyntheticCameraBackend for automated tests and hardware-free development.

Production platform:

- Raspberry Pi 5;
- Raspberry Pi Camera Module 3;
- Raspberry Pi OS;
- camera controlled using `rpicam-*` operating-system executables through
  Python subprocesses;
- CUPS;
- Canon Selphy CP740 as the intended printer;
- smartphone or another browser-based touch device as the booth interface.

The application should be approximately 90% complete and functional on a
development computer before Raspberry Pi-specific integration begins.

# Important architecture decisions

Treat the following as version 1 decisions unless a concrete blocking issue is
found.

## Raspberry Pi camera

Do not use Picamera2 in version 1.

Raspberry Pi camera access is isolated behind `RpicamCameraBackend`.

Expected approach:

- `rpicam-vid` provides the long-lived preview;
- preview owns the camera while the booth is ready;
- preview stops before still capture;
- the application waits for the preview process to terminate;
- `rpicam-still` performs high-resolution still capture;
- preview remains stopped while the review screen is displayed;
- preview restarts when the user returns to booth mode or requests a retake.

The Python uv environment therefore has no Raspberry Pi-specific Python camera
binding.

This does not remove the Raspberry Pi OS dependency on rpicam-apps and
libcamera.

## PC camera

Use OpenCV through `OpenCVCameraBackend`.

## Automated tests

Use `SyntheticCameraBackend`.

Automated tests must not depend on:

- a webcam;
- Raspberry Pi hardware;
- rpicam executables;
- CUPS;
- a printer;
- Internet connectivity.

## Printing

Use:

- `NullPrinterBackend` on the development computer;
- `CupsPrinterBackend` on Raspberry Pi.

Prefer the standard CUPS CLI for version 1 when sufficient.

Do not assume that Canon Selphy CP740 compatibility is confirmed until tested
on the physical printer.

## Frontend

Use:

- Flask;
- Jinja2;
- HTML;
- CSS;
- vanilla JavaScript.

Do not introduce a frontend framework.

## Application infrastructure

Do not introduce:

- Docker;
- systemd;
- Redis;
- Celery;
- a worker queue;
- a cloud service;
- an external database;
- a plugin framework.

# Code quality requirements

The project's quality requirements intentionally focus on three areas:

1. complete Python type annotations;
2. complete and useful documentation;
3. behavioral tests.

Pyright is the static type checker.

pytest is the automated testing framework.

Do not add or recommend:

- Ruff;
- Black;
- Flake8;
- isort;
- formatting-only tooling.

Formatting and linting style are not project quality gates.

# Documentation requirements

Architecture documentation must establish explicit behavioral contracts.

It must describe:

- component responsibility;
- resource ownership;
- lifecycle boundaries;
- idempotency where relevant;
- concurrency expectations;
- exceptions exposed between architectural layers;
- process ownership;
- failure recovery;
- static type boundaries;
- hardware test boundaries.

For camera components in particular, clearly document:

- who owns the camera;
- who owns preview processes;
- how shutdown works;
- what happens during capture;
- when preview restarts;
- what happens after failure.

# Sources

Inspect only what is necessary for this architectural milestone.

Primary repository sources:

- `.github/copilot-instructions.md`;
- `.github/instructions/*.instructions.md`;
- `docs/architecture.md`;
- `docs/configuration.md`;
- `docs/camera-lifecycle.md`, if it already exists;
- existing repository structure.

External inspiration:

- https://github.com/lfpoulain/SimpleBooth
- https://github.com/pibooth/pibooth

Use external projects only for architectural inspiration and comparison.

Do not copy source code from them.

Do not attempt to reproduce their complete feature sets.

# Architecture review

Review the existing architecture for the following concerns.

## Layer boundaries

Confirm clear separation between:

1. Flask routes;
2. application services;
3. domain models;
4. camera backends;
5. printer backends;
6. filesystem storage;
7. browser UI.

Identify any dependency direction that could couple Flask directly to hardware.

## Camera contract

Confirm that CameraBackend can represent:

- synthetic camera;
- OpenCV webcam;
- rpicam subprocess camera.

The application-level contract must not expose:

- OpenCV matrices;
- VideoCapture;
- subprocess Popen;
- Raspberry Pi-specific Python objects.

## Printer contract

Confirm that PrinterBackend can represent:

- NullPrinterBackend;
- CupsPrinterBackend.

Application services and Flask routes must not depend on CUPS-specific
objects.

## Booth workflow

Confirm that the intended state model covers at least:

- IDLE;
- COUNTDOWN;
- CAPTURING;
- REVIEW;
- ERROR;
- SLIDESHOW.

Document allowed transitions.

## Photo lifecycle

Confirm architecture for:

- unpredictable photo identifiers;
- temporary capture file;
- validation;
- atomic publication;
- metadata;
- thumbnails;
- deletion.

## Download lifecycle

Confirm architecture for:

- unpredictable download token;
- token-to-photo relationship;
- expiration;
- revocation;
- deletion behavior;
- public base URL.

## Configuration

Confirm clear distinction between:

- startup configuration;
- runtime-editable configuration;
- secrets;
- backend capabilities;
- requested camera settings;
- effectively applied camera settings.

## Testability

For every hardware-dependent component, identify the boundary that automated
tests replace with a fake or mock.

The complete automated suite must remain runnable on a regular PC.

# Expected documentation

Review and, where required, update:

- `docs/architecture.md`;
- `docs/configuration.md`;
- `docs/camera-lifecycle.md`.

`docs/camera-lifecycle.md` must explicitly describe:

1. OpenCV backend lifecycle;
2. SyntheticCameraBackend lifecycle;
3. RpicamCameraBackend process lifecycle;
4. preview ownership;
5. preview-to-capture transition;
6. shutdown;
7. timeout and failure handling;
8. concurrency assumptions.

Do not create application code.

Do not add dependencies.

Do not modify `pyproject.toml`.

# Work method

Before editing:

1. inspect the relevant files;
2. summarize the current architecture in no more than ten bullets;
3. identify only material contradictions, missing decisions or risks;
4. list the documentation files that require changes.

Avoid repeating architecture sections that are already complete.

When editing:

1. preserve accepted decisions;
2. fill genuine documentation gaps;
3. resolve contradictions;
4. prefer a simple design over speculative abstraction;
5. explicitly mark hardware assumptions that require real-world validation.

# Expected final response

Keep the final response concise.

Include:

## Files changed

List only modified files.

## Decisions confirmed

List important architecture decisions that did not require changes.

## Decisions changed

For each changed architectural decision:

- previous decision;
- new decision;
- concrete reason.

If none changed, say so.

## Open risks

List only risks that cannot be resolved before implementation or hardware
testing.

## Readiness

State whether the project documentation is sufficiently defined to begin the
bootstrap milestone.

Stop after this architecture milestone.