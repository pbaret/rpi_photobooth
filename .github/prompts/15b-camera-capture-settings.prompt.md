---
agent: agent
description: Add configurable rpicam still-capture quality and autofocus settings
---

# Goal

Add a focused set of configurable `rpicam-still` capture settings to the
existing RpicamCameraBackend and administration interface.

At the end of this milestone, the administrator must be able to tune the most
relevant still-photo controls for a photobooth operating in relatively low
light with subjects approximately one to two metres from the Camera Module 3.

The settings must be:

- represented by typed domain models;
- validated server-side;
- persisted through the existing configuration system;
- exposed through the existing capability-driven camera administration UI;
- converted to allowlisted `rpicam-still` arguments;
- visible as requested and effective/applied values where that distinction is
  available.

Do not add arbitrary rpicam command-line arguments.

# Context

RpicamCameraBackend is already implemented and integrated.

The application already provides:

- typed camera settings;
- backend capabilities;
- capability-driven admin controls;
- Rpicam command construction;
- capture workflow;
- real Camera Module 3 integration;
- Pyright and pytest validation.

This milestone extends only the still-capture tuning controls.

The normal target setup is:

- Raspberry Pi 5;
- Raspberry Pi Camera Module 3;
- indoor or relatively low-light event environment;
- human subjects approximately one to two metres from the camera;
- subjects expected to remain still briefly after the countdown;
- smartphone white CAPTURING screen providing limited supplemental light.

The smartphone display must not be treated as a real photographic flash.

# Sources

Before editing, inspect:

- installed `rpicam-still --help` output;
- results of the Raspberry Pi diagnostics milestone;
- RpicamCameraBackend;
- still-command construction;
- CameraSettings;
- capability models;
- camera configuration;
- Admin > Camera;
- existing image-quality and autofocus settings;
- applicable repository instructions.

Only expose options confirmed by the installed `rpicam-still` executable.

If an option listed in this prompt is not available on the installed version,
do not fake support.

Report it as unsupported.

# Settings to support

Evaluate and implement the following still-capture controls where supported by
the installed rpicam version.

## Output

- output width;
- output height;
- JPEG quality through the existing JPEG-quality setting;
- denoise mode;
- HDR mode.

## Exposure

- shutter duration;
- analogue gain, represented by a single domain setting named `gain`;
- metering mode;
- exposure mode;
- EV compensation.

Do not expose both `gain` and `analoggain` as separate administrator settings.

They represent the same conceptual setting.

Use one canonical domain field and one canonical command-line form.

## White balance and rendering

- AWB mode;
- brightness;
- contrast;
- saturation;
- sharpness.

## Autofocus

- autofocus mode;
- autofocus range;
- autofocus speed;
- autofocus window;
- manual lens position;
- autofocus on capture.

## Diagnostics

- rpicam verbosity.

# Default low-light portrait profile

Introduce defaults appropriate for the expected booth setup.

Use the following values as the initial proposed profile, subject to validation
against the installed executable and existing domain bounds:

- width: `4608`;
- height: `2592`;
- JPEG quality: `95`;
- shutter: automatic;
- gain: automatic;
- metering: `centre`;
- exposure mode: `normal`;
- EV compensation: `0.3`;
- AWB mode: `auto`;
- brightness: `0.0`;
- contrast: `1.0`;
- saturation: `1.0`;
- sharpness: `1.1`;
- denoise: `cdn_hq`;
- autofocus mode: `auto`;
- autofocus range: `normal`;
- autofocus speed: `fast`;
- autofocus window: `0.2,0.15,0.6,0.7`;
- autofocus on capture: enabled;
- lens position: unset;
- HDR: `off`;
- verbosity: `2`.

If an automatic value is represented by omission rather than a literal CLI
argument, omit the corresponding argument.

For example, do not emit a fixed shutter or fixed gain argument when the
setting is automatic.

Do not pass zero merely as a substitute for omission unless that behavior is
explicitly supported and already used by the backend.

# Default-profile policy

Treat these values as starting defaults, not guarantees of optimal photographic
quality.

Document that final values require real-world tuning based on:

- room illumination;
- subject movement;
- camera position;
- event background;
- Camera Module 3 standard or wide variant;
- visible noise;
- motion blur;
- white-balance consistency.

Do not describe the profile as universally optimal.

# Optional manual exposure

Allow the administrator to choose between:

- automatic exposure;
- manually configured shutter and gain.

When automatic exposure is selected:

- do not emit `--shutter`;
- do not emit `--gain`;
- allow metering, exposure mode, EV and AWB controls to remain applicable where
  supported.

When manual exposure is selected:

- validate and emit configured shutter duration;
- validate and emit configured gain;
- clearly indicate that these values may cause underexposure, overexposure,
  noise or motion blur.

Use microseconds as the application-level shutter unit if that matches the
existing backend and rpicam behavior.

Display the unit clearly in administration.

# Autofocus behavior

Use autofocus on capture as the default still-capture behavior.

The intended default sequence is:

1. enter the existing CAPTURING state;
2. display the existing white `Ne bougez plus` screen;
3. stop preview according to the existing backend lifecycle;
4. invoke `rpicam-still` with automatic autofocus and autofocus-on-capture;
5. capture the JPEG;
6. continue to REVIEW.

Do not alter the existing white-screen paint behavior or capture workflow.

# Autofocus consistency rules

Validate combinations before command construction.

## Automatic autofocus

When autofocus mode is `auto`:

- autofocus-on-capture may be enabled;
- autofocus range may be configured;
- autofocus speed may be configured;
- autofocus window may be configured;
- manual lens position must not be emitted.

## Continuous autofocus

When autofocus mode is `continuous`:

- do not assume that autofocus-on-capture is required;
- follow actual installed rpicam behavior;
- do not emit a manual lens position.

## Manual focus

When autofocus mode is `manual`:

- manual lens position may be configured;
- autofocus-on-capture must not be emitted;
- autofocus-window behavior should be disabled or ignored if not meaningful.

Reject or clearly normalize inconsistent combinations.

Do not silently emit conflicting arguments.

# Autofocus window

Represent the autofocus window as a typed normalized rectangle.

The model must include:

- x;
- y;
- width;
- height.

Validate:

- `0.0 <= x <= 1.0`;
- `0.0 <= y <= 1.0`;
- `0.0 < width <= 1.0`;
- `0.0 < height <= 1.0`;
- `x + width <= 1.0`;
- `y + height <= 1.0`.

The default is:

- x: `0.2`;
- y: `0.15`;
- width: `0.6`;
- height: `0.7`.

Serialize the value to the exact format expected by the installed
`rpicam-still`.

Do not expose an unvalidated free-text command argument.

# HDR behavior

Expose only HDR values supported by the installed executable.

Expected values may include:

- off;
- auto;
- sensor;
- single-exp.

Use `off` as the default photobooth value.

Document that HDR may affect:

- capture latency;
- motion artifacts;
- exposure behavior;
- hardware compatibility.

Do not claim all modes are supported by Camera Module 3 merely because the
command-line parser lists them.

# Image-rendering bounds

Use explicit backend capability bounds based on installed rpicam behavior.

At minimum validate:

- brightness within `-1.0` to `1.0`;
- positive contrast values within a conservative supported range;
- saturation within a conservative supported range;
- positive sharpness within a conservative supported range;
- EV within a conservative supported range;
- positive gain when manually configured;
- positive shutter duration when manually configured;
- positive image dimensions;
- JPEG quality within the existing accepted range.

Do not invent very broad ranges simply because the CLI accepts a floating-point
value.

If the installed tool does not expose a reliable bound, use a conservative
application bound and document it.

# Admin UI

Extend the existing capability-driven Admin > Camera section.

Do not create a Rpicam-specific administration page.

Show these controls only when declared by the active backend.

Group them into clear sections:

## Image

- width;
- height;
- JPEG quality;
- denoise;
- HDR.

## Exposure

- automatic/manual exposure selection;
- shutter duration;
- gain;
- metering;
- exposure mode;
- EV compensation.

## White balance and rendering

- AWB;
- brightness;
- contrast;
- saturation;
- sharpness.

## Autofocus

- autofocus mode;
- autofocus range;
- autofocus speed;
- autofocus-on-capture;
- autofocus window;
- manual lens position.

## Diagnostics

- verbosity.

Use appropriate native HTML controls:

- select for enum values;
- checkbox for booleans;
- number input for bounded numeric values.

Show units where relevant.

# Dynamic admin behavior

Use minimal vanilla JavaScript where useful to make invalid combinations
difficult to enter.

For example:

- disable shutter and gain inputs in automatic exposure mode;
- enable them in manual mode;
- show lens position only in manual autofocus mode;
- hide or disable autofocus-on-capture in manual mode.

Server-side validation remains mandatory.

Do not rely solely on JavaScript.

# Verbose command diagnostics

Use verbosity level `2` for the default Rpicam still-capture profile.

Add the corresponding allowlisted argument to `rpicam-still`.

In addition, explicitly log the complete command argument list immediately
before execution.

Use a safe readable representation such as `shlex.join(command)` for logging.

The subprocess must still execute the original argument list with
`shell=False`.

Do not reconstruct and execute the logged command string.

Log at an appropriate diagnostic level.

Do not include secrets, download tokens or arbitrary user-controlled values in
logs.

Camera settings and application-controlled temporary paths are acceptable when
properly validated.

# Requested versus effective values

Preserve the existing distinction between:

- requested configuration;
- validated value;
- command argument emitted;
- command accepted;
- photographically effective value.

The backend can normally confirm the argument emitted and process result.

Do not claim that brightness, autofocus, gain or HDR had the desired visual
effect solely because `rpicam-still` exited successfully.

Where useful, expose the final emitted command settings in protected
diagnostics.

Do not expose them on participant-facing pages.

# Persistence and backward compatibility

Persist the new values using the existing typed configuration architecture.

Existing configuration files that do not contain these fields must continue to
load using the documented defaults.

Do not overwrite a valid existing configuration merely because new fields are
missing.

Do not store raw command-line fragments.

# Toolchain

Do not add dependencies.

Use:

- existing typed domain models;
- existing Rpicam command construction;
- standard-library `shlex` for readable command logging;
- existing Flask/Jinja/JavaScript admin stack.

Do not add:

- Picamera2;
- arbitrary shell execution;
- frontend framework;
- schema framework;
- linting or formatting tools.

Do not change the build backend.

# Documentation

Follow repository-wide typing and documentation requirements.

Document:

- purpose and units of every setting;
- automatic versus manual exposure behavior;
- default low-light portrait profile;
- why shutter and gain remain automatic by default;
- motion-blur versus noise trade-off;
- autofocus mode interactions;
- autofocus-window coordinate system;
- HDR limitations;
- requested versus effective-value limitations;
- safe command logging behavior.

Update `docs/configuration.md` and relevant camera documentation.

# Tests

Add or update pytest tests covering at least:

## Defaults

- complete default low-light profile;
- automatic shutter omission;
- automatic gain omission;
- verbosity level 2;
- default autofocus-on-capture;
- default HDR off;
- backward compatibility with older configuration.

## Command construction

- width and height;
- JPEG quality;
- metering;
- exposure mode;
- EV;
- AWB;
- brightness;
- contrast;
- saturation;
- sharpness;
- denoise;
- autofocus mode;
- autofocus range;
- autofocus speed;
- autofocus window;
- autofocus on capture;
- manual lens position;
- HDR;
- verbosity.

## Validation

- invalid dimensions;
- invalid JPEG quality;
- invalid brightness;
- invalid gain;
- invalid shutter;
- invalid enum values;
- invalid autofocus rectangle;
- rectangle extending beyond normalized bounds;
- lens position rejected or omitted outside manual autofocus;
- autofocus-on-capture rejected or omitted in manual mode;
- unsupported HDR mode;
- command-injection strings rejected.

## Admin

- capabilities displayed only for RpicamCameraBackend;
- valid values persist;
- invalid values do not persist;
- automatic/manual exposure controls;
- autofocus-dependent controls;
- restart-required or capture-only metadata displayed correctly.

## Logging

- final command is logged in readable form;
- execution still receives an argument list;
- `shell=True` is never used;
- bounded stderr behavior remains unchanged.

# Automated validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

The automated suite must remain hardware-independent and runnable on the
Windows development laptop.

# Real Raspberry Pi validation

After automated validation passes, perform real comparisons on the Raspberry
Pi using the Camera Module 3.

Create a controlled test scene with:

- the camera in its normal booth position;
- a subject or focus target approximately one to two metres away;
- representative low lighting;
- the intended white smartphone capture screen active.

Do not register calibration images in the normal event gallery if a diagnostic
capture path is available.

Compare at least:

## Default automatic profile

- automatic shutter;
- automatic gain;
- normal exposure;
- EV `0.3`;
- autofocus-on-capture;
- HDR off.

## Motion-oriented profile

- shutter near `16667` microseconds;
- gain approximately `4.0`;
- exposure mode `sport` where supported;
- HDR off.

## Static low-light profile

- shutter near `33333` microseconds;
- gain between `2.0` and `4.0`;
- normal exposure;
- HDR off.

These alternatives are validation presets, not additional required product
features.

For each comparison observe:

- focus accuracy;
- motion blur;
- visible noise;
- face/subject brightness;
- white balance;
- capture latency;
- delay on the white `Ne bougez plus` screen.

Do not declare a universal winner from a single image.

Select final defaults only after several representative captures.

# Expected result

Before editing:

1. inspect current Rpicam settings and capabilities;
2. inspect installed `rpicam-still --help`;
3. identify which requested settings are actually supported;
4. propose precise application validation bounds;
5. identify existing fields that should be reused rather than duplicated;
6. list files expected to change.

Then implement the milestone.

After implementation report only:

## Files changed

List changed files.

## Settings added

List:

- setting;
- type;
- unit;
- default;
- allowed values or bounds;
- emitted rpicam argument.

## Unsupported settings

List requested settings not implemented because the installed executable does
not support them.

## Command diagnostics

Show one representative logged command with temporary paths shortened or
sanitized where appropriate.

Do not expose secrets.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform.

## Real camera validation

For each tested profile report:

- focus;
- blur;
- noise;
- brightness;
- color;
- latency.

Clearly distinguish observation from preference.

## Recommended final defaults

If real testing was performed, state the defaults selected from the measured
results.

If real testing was not performed, keep the proposed low-light profile marked
as provisional.

Stop after this milestone.

Do not implement:

- new camera backends;
- Picamera2;
- CUPS;
- new participant workflows;
- unrelated UI redesign.