---
description: Rules for camera backend implementations
applyTo: "src/photobooth/camera/**/*.py,scripts/*camera*.py"
---

# Camera implementation rules

All camera code must implement the hardware-independent CameraBackend contract.

All components must be fully typed and documented according to the repository
instructions.

## Public abstraction

Do not expose implementation-specific objects through CameraBackend.

In particular, application code must not receive:

- OpenCV matrices;
- VideoCapture instances;
- Popen instances;
- operating-system file descriptors.

## Rpicam

Never use `shell=True`.

Separate:

1. settings validation;
2. command construction;
3. process execution;
4. process lifecycle management.

This separation must remain visible and testable.

Use:

- a long-lived process for preview;
- a finite process for still capture.

Preview must release camera ownership before still capture begins.

Do not provide a configuration option accepting arbitrary rpicam arguments.

Every supported camera setting must be explicitly mapped to an allowed
command-line option.

Process ownership and cleanup behavior must be thoroughly documented in
docstrings.

## OpenCV

Do not open a webcam during module import.

Start and stop operations must be idempotent.

Access to VideoCapture must be serialized when concurrent access is possible.

Automated tests must not require a physical webcam.

## Synthetic camera

Synthetic output must be a valid image.

The backend should implement the same observable lifecycle contract as the
real backends where practical.

Tests must remain deterministic.

## Tests

Hardware tests must use fake or mocked boundaries.

For rpicam test at least:

- preview startup;
- normal preview shutdown;
- repeated stop;
- capture;
- preview-to-capture transition;
- process timeout;
- non-zero process exit;
- missing executable;
- invalid settings;
- invalid image output;
- cleanup following exceptions.

Tests should verify subprocess argument lists for security-sensitive command
construction.