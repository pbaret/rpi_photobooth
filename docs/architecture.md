# Photobooth architecture

## 1. Purpose

This document defines the architecture of the photobooth application.

The project is designed around two environments:

### Development environment

A regular laptop or desktop computer using:

- Python;
- Flask;
- uv;
- a built-in or USB webcam through OpenCV;
- a synthetic camera backend when no webcam is available.

The objective is to make approximately 90% of the complete photobooth
experience functional and testable on this environment.

### Production environment

A Raspberry Pi 5 using:

- Raspberry Pi OS;
- Raspberry Pi Camera Module 3;
- the operating-system `rpicam-*` applications;
- CUPS;
- a Canon Selphy CP740 printer;
- a smartphone or other touch-capable browser as the primary user interface.

The production environment must introduce the minimum possible amount of
Raspberry Pi-specific application code.

---

## 2. Design goals

The architecture prioritizes:

1. hardware independence for application logic;
2. complete development of the user experience on a PC;
3. simple deployment;
4. explicit resource ownership;
5. reliable camera lifecycle management;
6. complete Python type annotations;
7. complete behavioral documentation;
8. deterministic automated tests;
9. minimal dependencies;
10. simple diagnosis of hardware failures.

The application intentionally avoids unnecessary infrastructure.

The project does not require:

- Docker;
- systemd;
- Redis;
- Celery;
- a task queue;
- a server-side JavaScript framework;
- a frontend framework;
- a cloud service;
- an external database;
- a plugin framework.

---

## 3. High-level architecture

The application is divided into the following layers:

Application presentation:

    Flask routes
        |
        v
Application services:

    CaptureService
    GalleryService
    DownloadService
    SlideshowService
    DiagnosticsService
        |
        v
Domain abstractions:

    CameraBackend
    PrinterBackend
    domain models
    domain exceptions
        |
        v
Infrastructure implementations:

    SyntheticCameraBackend
    OpenCVCameraBackend
    RpicamCameraBackend

    NullPrinterBackend
    CupsPrinterBackend

Flask must never access hardware directly.

Application services depend on hardware abstractions rather than concrete
hardware implementations.

---

## 4. Repository structure

Target structure:

    photobooth/
    ├── .github/
    │   ├── copilot-instructions.md
    │   ├── instructions/
    │   └── prompts/
    ├── docs/
    │   ├── architecture.md
    │   ├── camera-lifecycle.md
    │   ├── configuration.md
    │   └── troubleshooting.md
    ├── src/
    │   └── photobooth/
    │       ├── app.py
    │       ├── config.py
    │       ├── domain/
    │       ├── camera/
    │       ├── printing/
    │       ├── services/
    │       ├── routes/
    │       ├── templates/
    │       └── static/
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   └── fixtures/
    ├── scripts/
    ├── data/
    ├── pyproject.toml
    └── README.md

---

## 5. Flask application

The application uses the Flask application factory pattern.

The main entry point is:

    create_app()

The application factory is responsible for:

- loading configuration;
- selecting infrastructure backends;
- creating application services;
- registering Flask Blueprints;
- registering application lifecycle cleanup.

The application is divided into three primary Blueprints.

### booth

Responsible for the photobooth user experience:

- ready screen;
- camera preview;
- countdown;
- capture trigger;
- transition to review;
- slideshow.

### media

Responsible for:

- image display;
- thumbnails;
- QR code generation;
- photo download.

### admin

Responsible for:

- configuration;
- camera settings;
- printer configuration;
- diagnostics.

Routes are HTTP adapters only.

Routes must not implement:

- camera access;
- subprocess execution;
- filesystem storage rules;
- printer logic;
- workflow state transitions beyond delegating to services.

---

## 6. Application services

### CaptureService

Responsible for:

- capture workflow;
- capture operation identifiers;
- preventing simultaneous captures;
- booth state transitions related to capture;
- invoking CameraBackend;
- validating capture results;
- handing completed captures to GalleryService.

It must not know whether the camera uses OpenCV or rpicam.

### GalleryService

Responsible for:

- photo identity;
- photo metadata;
- filesystem location resolution;
- thumbnail generation;
- deletion;
- listing photos;
- selecting slideshow content.

HTTP clients never provide filesystem paths.

### DownloadService

Responsible for:

- generating unpredictable download tokens;
- associating a token with a photo;
- checking expiration;
- revoking tokens;
- resolving downloads.

DownloadService persists one versioned JSON record per random token beneath
`data_root/metadata/download_tokens`. Each record contains one photo ID, a UTC
expiration instant, and a revocation flag. The configured lifetime is measured
from token creation; a token is expired when the current UTC instant is equal
to or later than its expiration. Revocation is persisted atomically. Every
download also resolves the original through GalleryService, so deleting the
photo makes all of its tokens unusable even though token records are retained.

### SlideshowService

Responsible for:

- providing eligible slideshow photos;
- excluding deleted photos;
- handling empty galleries.

Browser-side inactivity detection remains a UI concern.

### DiagnosticsService

Responsible for presenting useful health information without exposing
implementation secrets.

Possible diagnostics include:

- active camera backend;
- camera availability;
- number of stored photos;
- available storage;
- configured public base URL;
- printer availability;
- last capture status;
- last print status.

---

## 7. Domain layer

The domain layer contains implementation-independent models and exceptions.

Expected models include:

- CameraSettings;
- CameraCapabilities;
- CameraStatus;
- CaptureResult;
- PhotoMetadata;
- PrinterStatus;
- PrintResult;
- BoothState.

Domain code must not import:

- Flask;
- OpenCV;
- subprocess implementation objects;
- CUPS-specific implementation objects.

---

## 8. Camera abstraction

Camera access is represented through CameraBackend.

Conceptually, the backend provides operations such as:

    start() -> None

    stop() -> None

    get_preview_frame() -> bytes

    capture(
        output_path: Path,
        settings: CameraSettings,
    ) -> CaptureResult

    get_capabilities() -> CameraCapabilities

    get_status() -> CameraStatus

The exact interface is defined during the camera-contract milestone.

The contract must document:

- which operations require a started backend;
- idempotency;
- resource ownership;
- thread-safety;
- domain-level errors for unavailable hardware, invalid settings, failed
    operations, and timeouts where applicable;
- lifecycle transitions.

Implementation-specific objects must not escape through this interface.
The backend owns any camera handle or child process it creates. The service
owns the application-controlled output path and is responsible for validating
and publishing the resulting image.

---

## 9. Camera backends

### SyntheticCameraBackend

Purpose:

- automated tests;
- UI development without hardware;
- deterministic diagnostics.

It generates valid JPEG preview and capture images.

It should mimic the observable lifecycle of a real camera where practical.

### OpenCVCameraBackend

Purpose:

- PC development with a laptop or USB webcam.

OpenCV owns the webcam through VideoCapture.

The backend is responsible for:

- opening the configured camera index;
- retrieving preview frames;
- JPEG encoding;
- still captures;
- requested versus effective resolution;
- preview mirroring;
- resource cleanup;
- synchronization around VideoCapture.

The webcam must not be opened during module import.

### RpicamCameraBackend

Purpose:

- Raspberry Pi 5;
- Raspberry Pi Camera Module 3.

The backend does not use Picamera2.

It controls operating-system `rpicam-*` processes using the Python subprocess
API.

Responsibilities are divided into:

- `rpicam-vid` for preview;
- `rpicam-still` for high-resolution still capture.

The Python environment therefore contains no Raspberry Pi-specific Python
camera binding.

The system still depends on:

- Raspberry Pi OS;
- rpicam-apps;
- libcamera;
- correctly detected camera hardware.

---

## 10. Raspberry Pi camera lifecycle

Camera ownership must remain exclusive.

Initial lifecycle:

    booth enters ready mode
            |
            v
    start rpicam-vid
            |
            v
    preview available
            |
            v
    user starts capture
            |
            v
    countdown
            |
            v
    stop rpicam-vid
            |
            v
    wait for process termination
            |
            v
    execute rpicam-still
            |
            v
    validate captured JPEG
            |
            v
    enter REVIEW
            |
            v
    keep preview stopped

When the user returns to the booth or requests a retake:

    REVIEW
        |
        v
    booth ready mode
        |
        v
    restart rpicam-vid

The application must not intentionally run `rpicam-vid` and `rpicam-still`
concurrently against the same camera.

The detailed lifecycle is documented separately in:

    docs/camera-lifecycle.md

---

## 11. Rpicam command safety

Rpicam commands must use lists of arguments.

For example, conceptually:

    [
        "rpicam-still",
        "--output",
        "/path/to/file.jpg",
    ]

The implementation must never use:

    shell=True

HTTP clients and admin forms must never provide arbitrary command-line
arguments.

Supported camera controls are converted to command-line arguments through an
explicit mapping maintained by RpicamCameraBackend.

Finite subprocess operations require timeouts.

Process errors are converted into application domain exceptions.

Raw process errors must not be returned directly to HTTP clients.

---

## 12. Camera configuration and capabilities

The application distinguishes between four concepts:

### Requested value

The configuration desired by the administrator.

### Capability

What the active backend reports that it supports.

### Validated value

A requested value accepted according to the backend's declared capabilities.

### Effective value

A value that the backend was actually able to apply or confirm.

This distinction is especially important because OpenCV and rpicam do not
necessarily expose the same controls.

The application must not claim that a setting is supported simply because a
configuration field exists.

---

## 13. Booth state machine

Expected states:

    IDLE
    COUNTDOWN
    CAPTURING
    REVIEW
    ERROR
    SLIDESHOW

Typical capture flow:

    IDLE
      |
      v
    COUNTDOWN
      |
      v
    CAPTURING
      |
      v
    REVIEW

Allowed transitions:

| From | To | Cause |
| --- | --- | --- |
| IDLE | COUNTDOWN | A capture request is accepted. |
| IDLE | SLIDESHOW | The inactivity timeout expires and slideshow is enabled. |
| IDLE | ERROR | A required camera or workflow operation fails. |
| COUNTDOWN | CAPTURING | The countdown completes. |
| COUNTDOWN | IDLE | The capture is cancelled before camera capture begins. |
| COUNTDOWN | ERROR | A required camera or workflow operation fails. |
| CAPTURING | REVIEW | Capture, validation, publication, metadata, and thumbnail work completes. |
| CAPTURING | ERROR | Capture or any required publication step fails. |
| REVIEW | IDLE | The user requests a retake or leaves review. |
| SLIDESHOW | IDLE | The first user interaction exits slideshow. |
| ERROR | IDLE | The user retries or returns after failed-operation cleanup. |

All other transitions are rejected. Entering ERROR releases operation-owned
resources and does not automatically start a new capture. Recovery returns to
IDLE; camera preview is started as part of returning to booth-ready operation.
The first interaction that exits SLIDESHOW is consumed and cannot also request
a capture.

Retake follows REVIEW -> IDLE -> COUNTDOWN. Inactivity follows IDLE ->
SLIDESHOW. Only one capture operation may run at a time; duplicate or
concurrent requests are rejected as an application-level conflict.

The state owner is the application service, not the browser or a Flask route.
The browser may display state but is not authoritative for transition
validation.

The first interaction used to exit the slideshow must not immediately trigger
a capture.

Inactivity is tracked in the booth page for pointer, keyboard, and wheel
activity and is armed only in IDLE. Leaving IDLE cancels that timer, so it
cannot affect the separate capture countdown. The first activity event during
SLIDESHOW is consumed before it can reach booth controls. The page fetches the
GalleryService thumbnail list on entry and refreshes it every minute while
active; an empty list leaves the instruction visible without rapid retries.

Only one capture operation may run at a time.

Duplicate or concurrent capture requests must be rejected.

---

## 14. Photo lifecycle

A photo has an opaque, unpredictable application identifier.

Filesystem names and HTTP identities must not be based on sequential integers.

Capture sequence:

1. allocate a photo identifier;
2. determine an application-controlled temporary path;
3. ask CameraBackend to capture;
4. validate that the resulting image is a valid JPEG;
5. atomically publish the file;
6. create metadata;
7. create a thumbnail;
8. expose the photo to the review page.

The browser never supplies the filesystem destination.

Temporary files are removed after failed capture or validation. A photo is not
available to gallery or download operations until its required original,
metadata, and thumbnail are ready. If a post-capture publication step fails,
the service removes incomplete artifacts where possible and reports failure;
it must not expose a partially published photo.

---

## 15. Photo metadata

Version 1 uses simple local metadata rather than a database server.

Metadata can be stored using JSON files controlled by GalleryService.

The current implementation stores one versioned JSON file per photo below
`data_root/metadata`, with JPEG originals below `data_root/photos` and
thumbnails below `data_root/thumbnails`. GalleryService owns ID validation,
all path derivation, serialization, and persistence. Photo IDs are generated
using cryptographically unpredictable URL-safe values; HTTP clients never
provide a path. Missing metadata means the photo is unknown or deleted, while
malformed metadata is a controlled storage error. The original and thumbnail
are staged and published before metadata; metadata is the availability marker.
Deletion removes metadata first, then removes the assets. If cleanup partially
fails, media routes still cannot resolve the photo, though inaccessible orphan
files may remain.

Thumbnails are generated from validated JPEG captures with Pillow and share
the original photo's deletion lifecycle. Retake returns to the booth without
deleting the reviewed photo or starting a countdown. Development printing uses
NullPrinterBackend: the review action reports that printing is not configured
and does not contact a device. CUPS and duplicate physical-job protection are
deferred to the printer integration milestone.

A metadata entry may include:

- photo identifier;
- capture timestamp;
- original file location;
- thumbnail location;
- camera backend;
- selected capture settings;
- relevant capture metadata;
- deletion state if required;
- download token metadata.

The exact serialization format may evolve without exposing filesystem
structure to HTTP clients.

---

## 16. QR download lifecycle

A QR code does not contain the photo filesystem path.

It contains an application URL using an unpredictable token.

Conceptually:

    http://photobooth.local/download/<random-token>

or an IP-based equivalent configured through `public_base_url`.

The token must be:

- unpredictable;
- associated with exactly one photo;
- revocable;
- optionally expiring.

When a photo is deleted, its download tokens become invalid.

The application must not silently use localhost for QR URLs intended for a
different device.

`public_base_url` must be an explicitly configured HTTP(S) origin reachable by
the scanning device. When absent, review remains usable and displays a clear
configuration error without issuing a token. QR images are generated locally
with qrcode and Pillow; photo bytes and tokens are not sent to an external
service. Download URLs are bearer capabilities intended only for a trusted
LAN, not an authentication mechanism.

---

## 17. Slideshow

The slideshow uses thumbnails instead of full-resolution original images.

This reduces:

- browser bandwidth;
- memory use;
- image decoding overhead.

The browser detects user inactivity.

After the configured delay it enters slideshow mode.

The display includes a message such as:

    Touchez l'écran pour démarrer

A first interaction exits slideshow mode.

That interaction is consumed and must not also trigger a photo capture.

---

## 18. Printer abstraction

Printing uses PrinterBackend.

Conceptually:

    get_status() -> PrinterStatus

    print_photo(
        photo_path: Path,
        request_id: str,
    ) -> PrintResult

### NullPrinterBackend

Used during PC development.

It provides predictable behavior without contacting a printer.

### CupsPrinterBackend

Used on Raspberry Pi.

Should not crash the booth if no printer are available.

Version 1 should prefer the system CUPS command-line interface when practical:

- lp;
- lpstat.

The application does not require a Python CUPS dependency unless the command
line interface proves insufficient.

Print requests must be protected against accidental duplicate submission.
The printer abstraction reports printer unavailability and print-operation
failure through application-level results or domain errors, not CUPS objects or
raw command output. A repeated request identifier must not submit a second
physical print.

Canon Selphy CP740 support remains unverified until tested with:

- the physical printer;
- its CUPS queue;
- the selected driver;
- target paper format;
- target orientation.

---

## 19. Configuration architecture

Configuration is divided into two categories.

### Startup configuration

Settings that define application infrastructure and secrets.

Examples:

- bind address;
- HTTP port;
- admin secret;
- data root;
- backend selection where appropriate.

Secrets must not be persisted in the normal editable JSON configuration.

### Runtime-editable booth configuration

Examples:

- booth name;
- countdown;
- inactivity timeout;
- preview settings;
- capture settings;
- QR base URL;
- slideshow behavior;
- printer queue.

Runtime configuration is persisted locally.

The detailed configuration model is documented in:

    docs/configuration.md

---

## 20. User interface

The UI is:

- browser-based;
- mobile-first;
- touch-first;
- usable in portrait and landscape;
- implemented using Jinja2, HTML, CSS and vanilla JavaScript.

No frontend framework is required.

---

## 21. Concurrency, errors, and test boundaries

The application factory owns the selected backend instances and registers
their shutdown. Application services serialize conflicting workflow
operations, including capture. Backend implementations serialize access to
non-thread-safe hardware handles. A route must not bypass those service and
backend boundaries.

Infrastructure failures are translated at the backend boundary to documented
domain-level failures or results. Services handle those outcomes and preserve
workflow invariants; routes translate service outcomes into HTTP responses.
Raw OpenCV, subprocess, operating-system, and CUPS errors are not part of the
application-facing contract and are not returned to clients. Timeouts and
cleanup failures must remain observable in diagnostics without exposing
secrets or raw implementation details.

Automated tests replace hardware at its owning boundary:

- camera-dependent service tests inject a deterministic
    `SyntheticCameraBackend` or a focused fake implementing `CameraBackend`;
- rpicam process-management tests replace the subprocess execution boundary
    with a fake, so no rpicam executable or Pi is required;
- printer-dependent service tests inject `NullPrinterBackend` or a fake
    implementing `PrinterBackend`; CUPS command behavior is tested through a
    mocked command boundary;
- filesystem workflows use temporary directories and controlled file
    failures.

Tests assert externally observable state, results, and resource cleanup. The
complete suite must run on a regular PC without a camera, rpicam, CUPS, a
printer, or network access. Physical camera behavior, real process behavior,
and printer compatibility remain hardware-validation activities.

Main views:

1. booth;
2. countdown/capture state;
3. review;
4. slideshow;
5. administration;
6. error state.

Primary touch targets should be large enough for comfortable touchscreen use.

The main booth view should avoid requiring scrolling.

---

## 21. Type safety

All production Python code must be completely typed.

Every function and method has:

- typed parameters;
- explicit return type.

Pyright is the static type checker.

The target is strict type checking while isolating unavoidable untyped
third-party boundaries.

`Any` is not used as a shortcut to bypass type design.

When an external package exposes weak typing, imprecision should be localized
inside its adapter.

For example:

    OpenCV typing limitations
            |
            v
    OpenCVCameraBackend
            |
            v
    precise CameraBackend types

---

## 22. Documentation policy

Documentation is a first-class project quality requirement.

Every Python module has a module docstring.

Every class is documented.

Every function and method, including private helpers, is documented.

Documentation should explain behavior that types alone cannot describe.

Important topics include:

- responsibility;
- lifecycle;
- idempotency;
- ownership;
- concurrency;
- side effects;
- exceptions;
- error recovery;
- external resource behavior.

Documentation must avoid meaningless repetition.

For example:

    """Stop the camera."""

is insufficient when the actual behavioral contract involves subprocess
termination and resource release.

---

## 23. Testing strategy

pytest is the automated test framework.

The automated test suite must run on a normal PC without:

- a physical webcam;
- Raspberry Pi hardware;
- rpicam-apps;
- CUPS;
- a printer;
- Internet access.

Hardware boundaries are tested through fakes or mocks.

Tests focus on observable behavior rather than implementation details.

Important scenarios include:

- startup;
- shutdown;
- hardware unavailable;
- duplicate capture;
- subprocess timeout;
- subprocess failure;
- resource cleanup;
- invalid identifiers;
- malformed images;
- deleted photos;
- expired download tokens;
- printer failure.

---

## 24. PC milestone

Before Raspberry Pi integration begins, the following must work on the
development computer:

- uv installation;
- Flask application;
- configuration;
- synthetic camera;
- OpenCV camera;
- MJPEG preview;
- touch UI;
- countdown;
- capture workflow;
- duplicate-capture protection;
- JPEG validation;
- review;
- delete;
- retake;
- thumbnail generation;
- null printer;
- QR code;
- download from a second LAN device;
- token revocation;
- slideshow;
- administration;
- camera setting capability model;
- diagnostics;
- Pyright;
- pytest;
- clean shutdown.

---

## 25. Raspberry Pi milestone

The Raspberry Pi phase should introduce only:

- rpicam diagnostics;
- RpicamCameraBackend;
- real Camera Module 3 control;
- real autofocus behavior;
- actual rpicam control support (all parameters should be configurable);
- preview performance validation;
- preview-to-still latency validation;
- CUPS;
- real Canon Selphy CP740 validation;
- long-running hardware stability validation.

---

## 26. Deployment philosophy

Deployment must remain simple.

The expected development launch is conceptually:

    uv run <application entry point>

The Raspberry Pi should use the same principle.

Version 1 intentionally does not require:

- Docker;
- systemd;
- Kubernetes;
- a reverse proxy;
- a process manager.

Operational complexity should only be introduced in response to a demonstrated
need.

---

## 27. Architectural decision rule

New abstractions, dependencies and infrastructure must solve a concrete
problem.

Before introducing a significant dependency or architectural layer, determine:

1. which current limitation it solves;
2. why existing project primitives cannot reasonably solve it;
3. whether it compromises PC testability;
4. whether it increases Raspberry Pi deployment complexity;
5. whether the resulting design remains fully typed and testable.

Prefer the smallest design that preserves clear hardware boundaries.