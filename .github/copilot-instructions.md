# Photobooth - GitHub Copilot instructions

## Project goal

Build a local, touch-first photobooth application.

Development target:

- regular laptop or desktop computer;
- webcam through OpenCV;
- synthetic camera for automated tests.

Production target:

- Raspberry Pi 5;
- Raspberry Pi Camera Module 3;
- camera controlled through `rpicam-*` subprocesses;
- CUPS printer;
- Canon Selphy CP740 as the intended printer.

The application should be approximately 90% functional on the development
computer before Raspberry Pi-specific integration begins.

## Technology stack

Use:

- Python;
- Flask and Jinja2;
- uv for Python dependency and command management;
- OpenCV for development webcam access;
- Pillow for image processing;
- qrcode for local download QR codes;
- pytest for automated tests;
- Pyright for static type checking;
- vanilla JavaScript and CSS.

Do not introduce unless explicitly requested:

- Picamera2;
- the legacy Python `picamera` package;
- Ruff;
- Black;
- Flake8;
- isort;
- React;
- Vue;
- Angular;
- Tailwind;
- Bootstrap;
- Docker;
- Redis;
- Celery;
- a plugin framework;
- a cloud service;
- systemd units.

## Code quality priorities

Code quality in this project is intentionally defined by:

1. complete and precise type annotations;
2. complete and useful documentation;
3. automated behavioral tests.

Formatting and linting style are not quality gates.

Do not spend implementation effort changing code purely for stylistic
formatting.

## Typing requirements

All Python production code must be fully typed.

Every function and method must have:

- types for every parameter;
- an explicit return type;
- `-> None` when no value is returned.

Prefer precise types over `Any`.

Avoid `Any` unless required at an untyped third-party boundary.

When `Any` is unavoidable, keep it localized at that boundary and document
why it cannot be typed more precisely.

Use appropriate Python typing constructs when they improve the architecture,
including:

- `Protocol`;
- dataclasses;
- enums;
- type aliases;
- generics where genuinely useful.

Do not introduce sophisticated typing constructs if a simpler precise type is
sufficient.

Hardware abstraction interfaces must be fully typed.

Application-level interfaces must not expose implementation-specific types
such as:

- OpenCV matrices;
- `subprocess.Popen`;
- CUPS implementation objects.

Pyright is the project's static type checker.

New code must pass:

`uv run pyright`

Do not silence Pyright errors with broad ignores merely to make the check pass.

## Documentation requirements

Documentation is a primary project requirement.

Every Python module must have a module-level docstring explaining:

- its responsibility;
- its place in the architecture when useful.

Every class must have a docstring explaining:

- its responsibility;
- its lifecycle where relevant;
- resources it owns where relevant;
- concurrency or thread-safety expectations where relevant.

Every function and method, including private methods, must have a useful
docstring.

Docstrings should document, as applicable:

- purpose;
- parameters whose semantics require explanation;
- return value;
- exceptions intentionally exposed to callers;
- side effects;
- resource ownership;
- lifecycle implications;
- concurrency constraints.

Do not create documentation that merely repeats the function name or its type
annotations.

For example, avoid documentation such as:

`Stop the camera.`

Prefer documentation explaining observable behavior:

- whether calling stop twice is valid;
- whether child processes are guaranteed to be terminated before return;
- what errors may be raised;
- what happens to owned resources.

Hardware integration code requires especially explicit documentation.

## Architecture

Use:

- a Flask application factory named `create_app`;
- Blueprints for booth, media and administration;
- application services for workflows;
- explicit domain models;
- explicit domain exceptions;
- hardware abstraction interfaces;
- dependency injection through the application factory or a small explicit
  container.

Avoid mutable module-level global state.

Flask routes must not implement hardware behavior directly.

## Camera abstraction

Application code depends on `CameraBackend`, not concrete implementations.

Expected implementations:

- `SyntheticCameraBackend`;
- `OpenCVCameraBackend`;
- `RpicamCameraBackend`.

Flask routes must never:

- import OpenCV directly;
- invoke rpicam directly;
- construct camera commands.

## Raspberry Pi camera design

Version 1 uses the operating-system `rpicam-*` executables through Python
subprocesses.

Do not use Picamera2.

Expected responsibilities:

- `rpicam-vid` provides the long-lived preview;
- `rpicam-still` performs high-resolution still capture.

The Python uv environment should not depend on Raspberry Pi-specific Python
camera bindings.

The application still depends on the Raspberry Pi operating-system camera
stack, including rpicam-apps and libcamera.

Raspberry Pi camera integration must remain isolated inside the rpicam backend
and diagnostic scripts.

## Rpicam lifecycle

The initial lifecycle is:

1. `rpicam-vid` owns the camera while the booth preview is active;
2. a capture request stops the preview process cleanly;
3. the application waits until the preview process terminates;
4. `rpicam-still` acquires the camera;
5. the still image is captured and validated;
6. the application enters review mode;
7. preview remains stopped during review;
8. preview restarts when returning to booth mode or requesting a retake.

Do not let preview and still-capture processes compete for ownership of the
camera.

Changes to this lifecycle must be documented in
`docs/camera-lifecycle.md`.

## Subprocess safety

Never use:

`shell=True`

Commands must be represented as argument lists.

Do not accept arbitrary rpicam command-line arguments from configuration,
HTTP requests or admin forms.

Supported rpicam settings must use an explicit allowlist.

Finite commands require explicit timeouts.

Subprocess failures must be translated into domain exceptions.

Child processes owned by the application must not remain orphaned.

Shutdown code must:

1. request graceful termination;
2. wait for termination;
3. terminate forcefully only when necessary;
4. wait again before returning.

## Photo storage

Use unpredictable photo identifiers.

Never derive public URLs from filesystem paths.

Captures must:

1. be written to a temporary file;
2. be validated;
3. be published using an atomic rename.

Generate separate slideshow thumbnails.

Deleted photos must no longer be downloadable.

Do not log:

- image contents;
- administrator secrets;
- download tokens.

## QR downloads

QR download tokens must be:

- unpredictable;
- associated with a photo;
- revocable;
- optionally expiring.

The download URL must use the configured public base URL.

Do not silently generate localhost URLs intended for use from another device.

Do not use external image hosting or cloud storage.

## Printing

Application code depends on `PrinterBackend`.

Expected implementations:

- `NullPrinterBackend`;
- `CupsPrinterBackend`.

PC development uses the null backend.

Raspberry Pi production uses CUPS.

Do not claim Canon Selphy CP740 compatibility until a real printer, CUPS
queue, driver and paper format have been tested.

## Web application

The booth interface is:

- mobile-first;
- touch-first;
- usable in portrait and landscape;
- implemented using HTML, CSS and vanilla JavaScript.

Do not introduce a frontend framework.

State-changing HTTP operations use POST.

Use Post/Redirect/Get where appropriate.

Never accept a filesystem path from an HTTP client.

Do not expose Flask debug mode while listening on the LAN.

## Tests

Use pytest.

Automated tests must run on a normal development computer without requiring:

- a webcam;
- Raspberry Pi hardware;
- rpicam executables;
- CUPS;
- a printer;
- Internet access.

Mock only external boundaries where practical.

Important behavior to test includes:

- normal operation;
- invalid inputs;
- unavailable hardware;
- subprocess failure;
- subprocess timeout;
- duplicate user actions;
- resource cleanup;
- invalid photo identifiers;
- token expiration or revocation;
- camera lifecycle transitions.

Tests should primarily verify observable behavior rather than internal
implementation details.

## Development workflow

Before changing code:

1. inspect only files relevant to the requested task;
2. briefly describe the existing behavior;
3. provide a concise implementation plan;
4. list files expected to change;
5. identify material assumptions or risks.

Avoid exploring unrelated repository areas.

During implementation:

1. remain strictly within the requested milestone;
2. make the smallest coherent change;
3. do not rewrite unrelated files;
4. use the existing architecture;
5. fully type new Python code;
6. fully document new Python components;
7. add or update relevant tests;
8. do not implement future milestones early.

After implementation:

1. briefly summarize the changed files;
2. run the smallest relevant pytest test set;
3. run `uv run pyright`;
4. run the complete pytest suite when appropriate;
5. provide a concise manual validation procedure;
6. identify behavior that could not actually be verified;
7. stop after the requested milestone.

Do not spend response tokens restating these repository instructions.

Keep implementation reports concise.