---
agent: agent
description: Stabilize the complete PC photobooth before Raspberry Pi integration
---

# Goal

Stabilize the complete PC implementation before beginning Raspberry Pi-specific
integration.

This is a hardening milestone.

Do not add new product functionality.

At the end of this milestone, everything that can reasonably be validated
without Raspberry Pi hardware should be considered stable.

The remaining work must be clearly identifiable as Raspberry Pi, rpicam,
CUPS or physical printer integration.

# Context

The application should now provide on PC:

- synthetic camera;
- OpenCV webcam;
- browser preview;
- countdown and capture;
- review;
- gallery;
- delete and retake;
- QR download;
- slideshow;
- administration;
- capability-driven camera settings;
- null printer behavior.

This milestone establishes the PC baseline that future Raspberry Pi work must
not regress.

# Scope

Inspect the complete existing application, but do not redesign working
components without a concrete problem.

Look specifically for:

- incomplete workflow transitions;
- inconsistent application state;
- duplicate user actions;
- camera lifecycle problems;
- resource leaks;
- configuration values persisted but not actually used;
- filesystem consistency problems;
- invalid photo or token access;
- error paths that prevent returning to IDLE;
- hardware-specific assumptions leaking outside adapters;
- behavior that cannot currently be tested on PC but should be;
- unnecessary dependencies.

Fix concrete problems discovered within existing functionality.

Do not implement future Raspberry Pi or CUPS functionality.

# End-to-end PC workflows

Verify the existing workflows as complete sequences rather than only isolated
components.

## Capture

Verify:

`IDLE -> COUNTDOWN -> CAPTURING -> REVIEW`

Check:

- duplicate capture protection;
- camera failure;
- capture failure;
- invalid image;
- recovery to a usable state.

## Review

Verify:

- captured photo is displayed;
- retake returns to a usable booth without deleting the previous photo;
- delete removes access to the photo and thumbnail;
- print placeholder behaves as expected;
- repeated actions produce controlled behavior.

## QR download

Verify:

- valid download;
- expired token;
- revoked token;
- deleted photo;
- public base URL configuration.

## Slideshow

Verify:

- inactivity transition;
- empty gallery;
- deleted photos excluded;
- wake-up returns to IDLE;
- wake-up interaction does not trigger capture;
- countdown and inactivity timers remain independent.

## Administration

Verify:

- authentication;
- configuration validation;
- configuration persistence;
- persisted settings are actually consumed by the relevant workflow;
- requested and effective camera settings remain distinguishable;
- secrets are not exposed.

# Camera lifecycle

Verify with SyntheticCameraBackend and OpenCVCameraBackend:

- startup;
- shutdown;
- repeated start/stop where supported by the contract;
- browser disconnect/reconnect;
- unavailable camera;
- recovery after camera error;
- clean application shutdown.

Do not require a physical webcam in automated tests.

OpenCV hardware behavior may additionally be manually smoke-tested.

# Configuration and storage

Verify:

- missing configuration;
- malformed configuration;
- atomic configuration update;
- invalid values;
- empty gallery;
- malformed metadata;
- corrupt image;
- storage failure where practical to simulate;
- no client-controlled filesystem paths.

# Documentation and typing audit

Inspect all Python production modules.

Ensure:

- every module has a useful docstring;
- every class is documented;
- every method and function is documented;
- all parameters are typed;
- all return values are explicitly typed;
- lifecycle and ownership contracts are explicit where relevant;
- broad `Any` types are removed or locally justified.

Do not inflate documentation with text that merely restates code or type
annotations.

# Test audit

Review existing tests before adding new ones.

Add tests only for meaningful behavior or failure paths that are currently
uncovered.

Prefer observable behavior over implementation-detail tests.

All automated tests must remain executable without:

- webcam hardware;
- Raspberry Pi;
- rpicam;
- CUPS;
- printer;
- Internet access.

# Toolchain

Do not add production dependencies.

Do not add:

- linting tools;
- formatting tools;
- coverage tooling;
- test frameworks beyond pytest;
- Raspberry Pi-specific Python dependencies.

Do not change the build backend.

# Validation

Execute:

`uv run pyright`

`uv run pytest`

Both must pass.

Also provide manual smoke-test procedures for:

1. SyntheticCameraBackend;
2. OpenCVCameraBackend;
3. complete browser workflow on PC;
4. QR download from a second LAN device.

# Raspberry Pi boundary

At the end, produce a concise list of behavior that cannot be validated on the
development PC.

Separate it into:

## Camera hardware

Examples include real rpicam availability, Camera Module 3 behavior, autofocus,
preview performance and preview-to-still transition.

## Printing hardware

Examples include CUPS availability, Canon Selphy CP740 queue, driver, paper
format and physical output.

Do not claim any of these behaviors are validated.

# Expected result

Before editing:

1. inspect the existing application and tests;
2. list concrete issues found;
3. distinguish actual defects from optional improvements;
4. state which files require changes.

Fix:

- actual defects;
- missing error handling that affects existing workflows;
- meaningful missing tests;
- typing violations;
- documentation violations.

Do not implement optional refactoring merely because it would be cleaner.

After implementation report only:

- defects found and fixed;
- tests added or changed;
- Pyright result;
- pytest result;
- manual smoke-test checklist;
- remaining Raspberry Pi-only behavior.

Stop after the PC baseline is stable.