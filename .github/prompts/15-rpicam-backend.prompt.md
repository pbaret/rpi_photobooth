---
agent: agent
description: Implement and validate the Raspberry Pi rpicam camera backend
---

# Goal

Implement `RpicamCameraBackend` and integrate it into the existing photobooth.

At the end of this milestone, the application must run on the target Raspberry
Pi 5 using the connected Raspberry Pi Camera Module 3.

Using configuration only, the application must be able to replace
OpenCVCameraBackend with RpicamCameraBackend and support the complete camera
workflow:

1. start the booth;
2. start a real Raspberry Pi camera preview;
3. display the preview in the existing browser booth;
4. start the existing countdown;
5. display the existing white CAPTURING screen;
6. stop the preview process safely;
7. capture a real high-resolution JPEG;
8. display the captured image in the existing REVIEW screen;
9. restart preview when returning to the booth or selecting Retake;
10. cleanly release every camera process during application shutdown.

The complete automated test suite must remain runnable on a normal development
PC without rpicam or Raspberry Pi hardware.

# Execution environment

This prompt is currently executed through VS Code Remote SSH on the target
Raspberry Pi.

Real Raspberry Pi validation may therefore be performed after the
implementation and automated tests pass.

Do not assume that tests executed successfully on the Raspberry Pi also prove
that the project remains hardware-independent.

All automated tests must continue to isolate the rpicam subprocess boundary so
they can also run on the Windows development laptop.

# Existing functionality to preserve

The application already provides and has validated:

- CameraBackend;
- SyntheticCameraBackend;
- OpenCVCameraBackend;
- camera factory and backend selection;
- camera capabilities;
- browser preview;
- capture state machine;
- countdown;
- white CAPTURING screen;
- browser-paint-before-capture behavior;
- REVIEW;
- Retake;
- gallery;
- administration;
- configurable camera settings;
- theme and layout customization.

Do not reimplement these features.

Do not modify the participant navigation, UI design or capture semantics unless
a concrete Raspberry Pi integration defect requires a minimal adjustment.

The new implementation must remain behind the existing CameraBackend contract.

Flask routes and application services must not invoke rpicam commands directly.

# Sources

Before editing, inspect:

- results and documentation produced by the Pi diagnostics milestone;
- `scripts/pi-diagnostics.sh`;
- `docs/architecture.md`;
- `docs/camera-lifecycle.md`;
- `docs/configuration.md`;
- CameraBackend;
- camera domain models and exceptions;
- camera factory;
- SyntheticCameraBackend;
- OpenCVCameraBackend;
- capture workflow;
- preview streaming implementation;
- camera capability model;
- administration camera settings;
- applicable repository instructions.

Use the actual executable paths, versions and options observed by the diagnostic
milestone.

Do not construct commands from assumptions when the installed rpicam tools can
be inspected directly.

# Preconditions

Before implementation, verify without modifying the system that:

- `rpicam-vid` is available;
- `rpicam-still` is available;
- the Camera Module is detected;
- the standalone still diagnostic succeeds;
- the standalone bounded stream diagnostic succeeds.

If a mandatory prerequisite fails:

1. report the failure;
2. do not install packages automatically;
3. do not attempt to hide the failure with mock production behavior;
4. continue with PC-compatible code and tests where practical;
5. clearly mark real hardware validation as blocked.

Do not execute:

- `sudo`;
- `apt install`;
- operating-system upgrades;
- `/boot` modifications;
- network configuration changes;
- systemd changes.

# Backend implementation

Implement `RpicamCameraBackend` as a concrete implementation of the existing
CameraBackend contract.

Do not change CameraBackend unless a concrete incompatibility is found.

If the contract must change:

1. explain the incompatibility before editing;
2. make the smallest coherent contract change;
3. update all existing backends;
4. update relevant tests;
5. preserve application-level hardware independence.

Do not expose through CameraBackend:

- `subprocess.Popen`;
- file descriptors;
- raw rpicam output;
- command-line arguments;
- Raspberry Pi-specific types.

# Process execution boundary

Create or reuse a small typed process-execution boundary that allows
RpicamCameraBackend to be tested deterministically without real executables.

The boundary must support the actual needs of this backend:

- finite command execution;
- long-lived process startup;
- standard-output access;
- bounded standard-error handling;
- process status;
- graceful termination;
- bounded waiting;
- forced termination fallback.

Do not create a general-purpose subprocess framework.

Keep the abstraction focused on camera-process lifecycle.

The production implementation uses Python standard-library subprocess APIs.

The tests use typed fakes.

# Subprocess security

Never use:

`shell=True`

Represent every command as a list of arguments.

Do not:

- build a shell command string;
- accept arbitrary rpicam arguments from configuration;
- expose a free-form arguments field in the admin UI;
- interpolate client-provided paths;
- trust unvalidated setting values.

Map camera settings to command-line options through explicit allowlisted code.

Use application-controlled paths.

Use finite timeouts for all finite commands and process shutdown operations.

# Preview implementation

Use `rpicam-vid` as the long-lived preview process.

Use the preview format and command options actually supported by the installed
rpicam version and observed during the diagnostics milestone.

The production preview output must be compatible with the existing Flask
browser-preview contract.

Before implementation, explicitly document the selected preview strategy:

- rpicam codec/output format;
- output destination;
- frame boundary detection;
- conversion, if any;
- expected CameraBackend frame representation.

Prefer an encoded format that avoids unnecessary Python decode/re-encode work
when it is supported by the installed rpicam version and compatible with the
existing browser MJPEG route.

Do not add an image/video transcoding dependency merely to compensate for an
unverified command assumption.

If the installed rpicam version cannot provide a suitable stream using the
current design, report the concrete incompatibility rather than inventing
unsupported options.

# Preview process ownership

RpicamCameraBackend owns the preview process.

Document and implement:

- when the process is created;
- how successful startup is detected;
- how premature exit is detected;
- how standard output is consumed continuously;
- how standard error remains bounded;
- which component extracts complete preview frames;
- how the latest preview frame is shared safely;
- what happens when no complete frame is available;
- how browser disconnection affects, or does not affect, the process;
- how application shutdown terminates it.

A browser connection must not own the physical preview process.

Multiple browser clients must not create multiple rpicam processes.

# Preview frame parsing

Implement robust frame-boundary handling for the selected encoded preview
format.

Do not assume:

- one process read equals one complete frame;
- frame boundaries align with pipe reads;
- every read returns data immediately.

The parser must handle:

- partial frames;
- multiple frames in one read;
- temporary absence of data;
- process exit;
- malformed or oversized buffered data.

Bound in-memory buffering so malformed output cannot cause unlimited memory
growth.

Keep parsing independently testable with deterministic byte sequences.

# Preview startup

`start()` must conform to the existing CameraBackend lifecycle contract.

It must:

1. validate mandatory executable availability through the injected process
   boundary or explicit availability check;
2. build the preview command;
3. start exactly one owned preview process;
4. begin bounded output and error consumption;
5. detect successful startup or fail within a configured timeout;
6. expose a usable preview frame before reporting readiness where the existing
   contract requires this;
7. clean up completely after startup failure.

Repeated `start()` calls must follow the idempotency semantics already defined
by CameraBackend.

Do not start rpicam during module import.

# Preview shutdown

`stop()` and internal preview shutdown must:

1. handle the already-stopped state;
2. signal graceful termination;
3. wait for a bounded period;
4. terminate more forcefully when required;
5. wait again;
6. kill only as the final fallback;
7. wait for final termination;
8. stop and join owned reader activity;
9. close owned streams where appropriate;
10. release all process references.

After successful stop, no preview process or owned reader activity may remain.

Document behavior if the child process cannot be terminated.

# Still capture

Use `rpicam-still` for high-resolution capture.

The backend must:

1. accept an application-controlled output path;
2. create or use an application-controlled temporary path;
3. construct an allowlisted argument list;
4. apply supported validated settings;
5. execute the finite command with a timeout;
6. capture bounded diagnostic error output;
7. handle missing executable;
8. handle non-zero exit;
9. handle timeout;
10. verify that output exists and is non-empty;
11. validate that the result is a decodable JPEG using the existing image
    validation mechanism;
12. atomically publish or return the capture according to the existing
    CameraBackend/GalleryService contract;
13. clean up temporary output after every failure path;
14. return the existing typed CaptureResult.

Do not write diagnostic or failed captures into the managed gallery.

Do not publish a partial or invalid image.

# Preview-to-capture lifecycle

Implement the documented exclusive camera lifecycle:

1. acquire the backend camera lifecycle lock;
2. refuse or serialize conflicting camera ownership operations according to the
   existing CameraBackend contract;
3. stop the preview process;
4. wait until preview has terminated;
5. confirm that owned preview-reading activity has stopped;
6. execute `rpicam-still`;
7. validate and publish the JPEG;
8. return CaptureResult;
9. remain without preview while the application is in REVIEW.

Do not restart preview immediately after successful capture.

The existing workflow must restart preview only when:

- the user returns to the booth;
- the user chooses Retake;
- another documented workflow explicitly re-enters the ready booth state.

Do not intentionally run `rpicam-vid` and `rpicam-still` simultaneously against
the same camera.

# Capture failure recovery

If still capture fails after preview has been stopped:

- clean up temporary files;
- leave no still or preview process running unintentionally;
- release the lifecycle lock;
- translate the error into the appropriate camera domain exception;
- preserve enough backend state for the existing workflow to recover safely.

Follow the existing application error semantics.

Do not automatically restart preview during an error path if doing so conflicts
with the existing workflow state.

If preview recovery is needed, let the documented workflow explicitly request
it.

# Application shutdown

Integrate backend shutdown with the existing application lifecycle.

Stopping Flask or the photobooth process must not leave:

- `rpicam-vid`;
- `rpicam-still`;
- output-reader activity;
- temporary capture files

owned by the application.

Do not add systemd or another process manager.

# Camera settings

Map only generic camera settings already represented by the existing typed
camera model.

Candidate controls may include, only when observed and supported by the
installed rpicam version:

- preview size;
- capture size;
- JPEG quality;
- autofocus mode;
- manual lens position;
- exposure time;
- analogue gain;
- exposure compensation;
- white-balance mode;
- colour gains;
- brightness;
- contrast;
- saturation;
- sharpness;
- denoise mode;
- flicker control;
- rotation or transform.

Do not implement a setting merely because it appears in generic documentation.

For each setting, distinguish:

- requested;
- valid according to the domain;
- supported by this backend;
- mapped to an installed rpicam option;
- effectively applied or only requested.

Reject unsafe or invalid values before command construction.

# Capabilities

Implement the RpicamCameraBackend capability declarations using the existing
capability model.

Expose only capabilities that the backend actually maps and that are supported
by the observed installed rpicam command set.

Do not hard-code capabilities in the administration layer.

The existing capability-driven admin UI should display RpicamCameraBackend
controls without backend-specific template changes.

Mark accurately:

- allowed values or bounds;
- default when known;
- read-only status;
- restart requirements;
- effective value availability.

Do not claim that command acceptance proves photographic effect or quality.

Hardware tuning remains a separate manual validation activity.

# Factory and configuration integration

Integrate `RpicamCameraBackend` into the existing camera factory.

The application must select it through the existing typed backend configuration,
conceptually:

`camera_backend = rpicam`

Do not introduce a second Raspberry Pi-specific application entry point.

Do not add Rpicam conditionals to:

- Flask routes;
- CaptureService;
- GalleryService;
- participant templates;
- admin templates beyond capability-driven generic behavior.

Switching between:

- synthetic;
- opencv;
- rpicam

must remain a configuration decision.

# Logging and diagnostics

Log useful lifecycle events without logging image data or unbounded process
output.

Useful events include:

- preview process start;
- preview readiness;
- preview shutdown;
- unexpected preview exit;
- still capture start;
- still capture success/failure;
- timeout;
- forced termination.

Do not expose raw stderr to participant-facing pages.

Preserve a bounded diagnostic message suitable for logs and protected
diagnostics.

# Toolchain

Do not add:

- Picamera2;
- legacy picamera;
- Raspberry Pi-specific Python camera dependencies;
- video transcoding dependencies;
- process-management dependencies;
- linting or formatting tools.

Use:

- Python standard-library subprocess APIs;
- the existing project dependencies;
- system-provided `rpicam-apps`.

Do not change:

- the build backend;
- the frontend toolchain;
- application deployment architecture.

Do not install or upgrade operating-system packages automatically.

# Documentation

Follow repository-wide typing and documentation requirements.

Document in detail:

- backend responsibility;
- backend state;
- physical camera ownership;
- preview-process ownership;
- process execution boundary;
- preview command strategy;
- preview frame parsing;
- bounded output buffering;
- bounded stderr behavior;
- process startup detection;
- graceful shutdown;
- forced termination fallback;
- lifecycle locking;
- preview-to-capture transition;
- capture timeout;
- temporary-file lifecycle;
- JPEG validation;
- failure recovery;
- preview restart responsibility;
- application shutdown behavior;
- capability declarations;
- settings mapping.

Every private lifecycle method must also have useful behavioral documentation.

Update `docs/camera-lifecycle.md` with the lifecycle actually implemented, not
the architecture originally anticipated if the two differ.

Update troubleshooting documentation with concrete errors observed during real
Pi validation.

# Automated tests

Use the typed process-execution boundary to keep all automated tests independent
from actual rpicam executables.

Tests must remain runnable on both:

- Windows development laptop;
- Raspberry Pi.

Do not mark hardware-dependent tests as ordinary unit tests.

Cover at least:

## Commands and settings

- preview command construction;
- still command construction;
- validated setting mapping;
- rejected invalid values;
- rejected command-injection values;
- application-controlled output paths;
- backend capability declarations.

## Preview output

- one complete frame;
- partial frame across several reads;
- multiple frames in one read;
- malformed data before a valid frame;
- bounded buffer behavior;
- no data before timeout;
- process exit while waiting for a frame.

## Preview lifecycle

- normal startup;
- repeated startup;
- startup timeout;
- startup process failure;
- premature process exit;
- normal shutdown;
- repeated shutdown;
- graceful termination timeout;
- forced termination;
- final kill fallback if represented by the process boundary;
- reader cleanup;
- stream cleanup;
- no orphan owned process after errors.

## Still capture

- successful still capture;
- missing executable;
- non-zero process exit;
- timeout;
- missing output;
- empty output;
- invalid JPEG;
- valid JPEG;
- temporary-file cleanup;
- CaptureResult contents.

## Preview-to-capture

- preview stops before still execution;
- still does not execute until preview termination is confirmed;
- no simultaneous camera ownership;
- preview does not restart after successful capture;
- lifecycle lock released after success;
- lifecycle lock released after failure;
- cleanup after every failure path.

## Application integration

- factory selects RpicamCameraBackend;
- non-Rpicam backends still work;
- capture workflow reaches REVIEW using a fake process runner;
- Retake requests preview restart through the existing workflow;
- no Flask route invokes rpicam directly.

# Automated validation

Execute on the current repository:

`uv run pyright`

`uv run pytest`

Both must pass.

The complete suite must not require real rpicam execution.

If the code is also synchronized back to the Windows development laptop,
rerun the same commands there before considering cross-platform automated
validation complete.

Do not claim Windows validation unless it was actually executed on Windows.

# Real Raspberry Pi validation

After automated validation passes, execute a real integration test on the
current Raspberry Pi using the actual RpicamCameraBackend.

Do not use mocks for this section.

Validate:

1. select `camera_backend = rpicam`;
2. start the application;
3. open the booth from the kiosk device or another LAN browser;
4. verify real live preview;
5. keep preview active for several minutes;
6. disconnect and reconnect the browser;
7. verify the backend does not create duplicate preview processes;
8. take one photo;
9. verify the existing countdown;
10. verify the existing white `Ne bougez plus` screen;
11. verify preview stops before still capture;
12. verify a valid real JPEG is produced;
13. verify navigation to REVIEW;
14. verify preview remains stopped during REVIEW;
15. choose Retake;
16. verify preview restarts;
17. take several successive photos;
18. return to the booth after delete/review actions;
19. stop the application;
20. verify no owned `rpicam-*` process remains.

Use system process inspection to verify that no orphan process remains.

Do not modify the operating system during validation.

# Camera Module 3 validation

Using only controls actually implemented by this milestone, validate where
available:

- autofocus mode;
- capture resolution;
- preview resolution;
- JPEG quality;
- one exposure-related setting;
- one image-processing setting.

For every control classify the result as:

- command mapping tested;
- command accepted by installed rpicam;
- visible/effective behavior manually observed;
- not validated.

Do not claim photographic effectiveness based only on a zero exit code.

# Performance observations

Record observed, approximate application-level behavior without introducing a
benchmarking framework.

Observe:

- time until first usable preview;
- preview responsiveness;
- time between countdown completion and REVIEW;
- time required to restart preview after Retake;
- whether the white capture screen duration is acceptable;
- obvious CPU or memory problems;
- unexpected process growth.

Do not prematurely optimize without an observed problem.

If a hardware-driven UX adjustment is necessary, report it separately before
changing the previously validated UI.

# Failure validation

Where safe, validate at least one controlled real failure, such as temporarily
selecting an invalid executable path through a test-only configuration or
stopping the test process.

Do not disconnect the camera ribbon while the Raspberry Pi is powered.

Verify that:

- the participant receives the existing recoverable error experience;
- the application logs useful diagnostics;
- no process or temporary file remains;
- the booth can recover through the documented workflow.

Do not make persistent system modifications for failure testing.

# Expected result

Before editing:

1. confirm that the workspace is running on the Raspberry Pi;
2. inspect diagnostic results and installed rpicam help/version output;
3. inspect the existing CameraBackend and camera lifecycle;
4. describe the exact preview-stream format and parsing strategy;
5. describe the process-runner interface;
6. describe preview ownership and shutdown;
7. describe preview-to-capture ordering;
8. list settings that will actually be supported;
9. list files expected to change.

Then implement the complete milestone without asking for additional
confirmation.

After implementation report only:

## Files changed

List repository files changed.

## Backend design

Summarize:

- process boundary;
- preview strategy;
- frame parsing;
- lifecycle and ownership;
- capture strategy.

## Supported capabilities

List only the settings actually implemented and declared by
RpicamCameraBackend.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform on which each was executed.

## Real Raspberry Pi validation

For each item report PASS, FAIL or SKIP:

- preview startup;
- browser preview;
- browser reconnect;
- still capture;
- REVIEW;
- Retake preview restart;
- repeated captures;
- application shutdown;
- no orphan process;
- implemented Camera Module 3 controls.

## Observed timings

Report the approximate observed durations relevant to UX.

## Limitations

List only behavior not actually validated.

## Readiness

Conclude with exactly one of:

- `RPICAM BACKEND READY`
- `RPICAM BACKEND NOT READY`

If not ready, list the blocking failures.

Stop after RpicamCameraBackend integration.

Do not implement:

- Picamera2;
- CUPS;
- printer integration;
- hotspot configuration;
- systemd;
- new participant workflows;
- unrelated UI redesign.