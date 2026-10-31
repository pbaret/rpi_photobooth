---
agent: agent
description: Validate Raspberry Pi camera environment before backend integration
---

# Goal

Validate the real Raspberry Pi camera environment before implementing
RpicamCameraBackend.

This milestone must establish that the following stack works independently of
the photobooth application:

Raspberry Pi 5
  -> Raspberry Pi OS
  -> rpicam-apps / libcamera
  -> Camera Module 3

This prompt is being executed from VS Code connected to the target Raspberry Pi
through Remote SSH.

Perform real read-only diagnostics on this Raspberry Pi.

Do not implement RpicamCameraBackend yet.

# Context

The complete photobooth application is already validated on the development
PC using SyntheticCameraBackend and OpenCVCameraBackend.

The production camera backend will later control:

- `rpicam-vid` for preview;
- `rpicam-still` for high-resolution capture.

The application intentionally does not use Picamera2.

The purpose of this milestone is to separate operating-system/hardware problems
from future application integration problems.

At the end of this milestone we should know whether rpicam can successfully
control the connected Camera Module 3 without Flask or the photobooth
application being involved.

# Safety boundary

You may execute read-only or non-destructive diagnostic commands directly on
the Raspberry Pi.

You may also create temporary diagnostic images or short-lived camera
processes required to validate the camera.

You must not automatically execute:

- `sudo`;
- `apt install`;
- `apt upgrade`;
- `apt full-upgrade`;
- `rpi-update`;
- `raspi-config` modifications;
- modifications under `/boot`;
- network configuration changes;
- systemd configuration changes;
- CUPS configuration;
- permission/group modifications.

If a missing package or system configuration change is required, stop that
specific diagnostic step and report the exact command the user could execute
manually.

Continue with all other diagnostics that remain possible.

Do not modify the operating system to make a test pass.

# Environment discovery

Inspect and record:

- operating system name and version;
- architecture;
- Raspberry Pi model;
- kernel version;
- Python version;
- uv availability and version;
- available disk space relevant to the project.

Use system-provided commands.

Do not install tooling for discovery.

# Rpicam discovery

Determine whether the expected executables are available:

- `rpicam-hello`;
- `rpicam-still`;
- `rpicam-vid`.

For each available executable, record:

- resolved executable path;
- version information where supported.

Do not assume installation locations.

Use normal executable discovery such as `command -v`.

Do not depend on legacy commands such as:

- `raspistill`;
- `raspivid`;
- `libcamera-still`;
- `libcamera-vid`.

The production design targets current `rpicam-*` command names.

# Camera discovery

Determine whether the Raspberry Pi camera stack detects a camera.

Use supported rpicam functionality where available.

Record enough information to identify:

- whether at least one camera is detected;
- detected camera/sensor identity where reported;
- advertised modes/resolutions where useful for the next milestone.

Do not parse more information than RpicamCameraBackend is likely to need.

# Basic camera validation

If the required rpicam executables and a camera are available, perform real
non-destructive camera tests.

## Still capture

Capture one temporary JPEG using `rpicam-still`.

Use a temporary diagnostic path outside the managed photobooth gallery.

Verify:

- command exits successfully;
- output file exists;
- output file is non-empty;
- output is recognized as an image using tools already available on the
  machine where practical.

Do not register the diagnostic image in GalleryService.

Clean up temporary diagnostic files after successful validation.

## Preview/video process

Perform a short bounded `rpicam-vid` diagnostic suitable for an SSH/headless
environment.

Do not rely on a graphical preview window being available over SSH.

Use an option/mode appropriate for verifying that:

- the process starts;
- the camera can stream;
- the process can terminate normally.

Keep the test short and bounded.

Do not leave rpicam processes running after the diagnostic.

# Camera Module 3 preparation

Gather information useful for the future RpicamCameraBackend, but do not
implement that backend yet.

In particular, determine from the installed rpicam tools where practical:

- autofocus-related command-line options;
- still-capture resolution/mode information;
- preview/video format options relevant to producing a browser preview;
- available controls that correspond to the existing generic CameraSettings
  model.

Do not claim a control is supported merely because it is expected from generic
documentation.

Distinguish:

- options observed on the installed Raspberry Pi;
- options known only from project documentation;
- options not yet validated.

Do not perform exhaustive camera tuning in this milestone.

# Preview-to-still boundary

Do not implement the production preview-to-capture lifecycle yet.

However, if basic individual `rpicam-vid` and `rpicam-still` tests succeed,
record that the next milestone still needs to validate the application-level
sequence:

`rpicam-vid running`
  -> stop
  -> wait for release
  -> rpicam-still
  -> capture
  -> later restart preview

Do not mark this transition as validated merely because the two commands work
individually.

# Permissions

Identify the current user and relevant permissions affecting camera access.

Do not modify:

- groups;
- device permissions;
- udev rules.

If camera access fails because of permissions, report the evidence and the
manual remediation required.

# Diagnostic script

Create or update:

`scripts/pi-diagnostics.sh`

The script must reproduce the useful non-destructive environment and camera
checks from this milestone.

Requirements:

- run without root;
- never use `sudo`;
- never install software;
- never modify system configuration;
- clearly separate PASS, FAIL and SKIP results;
- continue after non-fatal failures where possible;
- return a non-zero exit status when mandatory camera prerequisites fail;
- clean up temporary files and processes it creates;
- not require the Flask application to be running;
- not modify application photo storage.

Keep the script straightforward and readable.

Do not build a generic diagnostics framework.

# Documentation

Update the existing Raspberry Pi/troubleshooting documentation where
appropriate.

Document:

- Raspberry Pi OS environment observed;
- required rpicam executables;
- how executable availability is detected;
- camera detection method;
- permissions assumptions;
- basic manual still diagnostic;
- basic manual preview/video diagnostic;
- how to interpret failures.

Clearly distinguish:

## System/hardware failures

Examples:

- rpicam executable missing;
- no camera detected;
- Camera Module inaccessible;
- rpicam still capture fails independently.

These are below the photobooth application boundary.

## Application failures

If standalone rpicam diagnostics succeed but the future RpicamCameraBackend
fails, investigation should start at:

- command construction;
- subprocess lifecycle;
- preview stream parsing;
- camera ownership transition;
- settings mapping.

# Toolchain

Do not add Python dependencies.

Do not add Raspberry Pi-specific Python packages.

Do not add Picamera2.

Do not change the Python build system.

Do not add linting or formatting tools.

Use system-provided diagnostic commands and existing project tooling.

# Validation

Run the diagnostic script on this Raspberry Pi.

Record its actual result.

If camera hardware is available, independently verify at least:

- camera detection;
- one still capture;
- one bounded preview/video process.

Also run the existing software quality checks if the current Pi project
environment is already ready to do so without installing additional
dependencies:

`uv run pyright`

`uv run pytest`

If the Python environment has not yet been configured on the Pi, report that
fact instead of changing the system or project environment solely for this
milestone.

Do not misrepresent skipped checks as successful checks.

# Expected result

Before editing:

1. confirm that the current VS Code workspace is running on the Raspberry Pi
   rather than the Windows development laptop;
2. inspect the relevant existing scripts and documentation;
3. list the diagnostic commands you intend to run;
4. identify which commands create temporary files or short-lived processes.

Then execute the safe diagnostics and implement the reusable diagnostic script.

After implementation report only:

## Environment

- Raspberry Pi model;
- Raspberry Pi OS version;
- architecture;
- relevant tool versions.

## Camera stack

For each item report PASS, FAIL or SKIP:

- `rpicam-hello` available;
- `rpicam-still` available;
- `rpicam-vid` available;
- camera detected;
- still capture successful;
- bounded preview/video successful.

## Camera information

Report only useful observed information for the future backend, including
camera identity and relevant command capabilities.

## Files changed

List repository files changed.

## Manual actions required

List only system changes or installations that require explicit user action.

Do not execute them.

## Readiness for milestone 15

Conclude with exactly one of:

- `READY FOR RPICAM BACKEND`
- `NOT READY FOR RPICAM BACKEND`

If not ready, list the blocking failures.

Stop after diagnostics and documentation.

Do not implement RpicamCameraBackend.