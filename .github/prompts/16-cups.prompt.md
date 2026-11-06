---
agent: agent
description: Implement CUPS printing and configurable Canon SELPHY CP1000 settings
---

# Goal

Implement `CupsPrinterBackend` and integrate it into the existing photobooth
printing workflow.

At the end of this milestone, the application must be able to:

1. discover the configured CUPS printer queue;
2. validate that the queue exists and is available;
3. submit the reviewed JPEG to CUPS;
4. retrieve and store the returned CUPS job identifier;
5. prevent duplicate print submissions;
6. expose useful print status to the existing REVIEW screen;
7. allow printing settings to be configured from Admin > Printing.

The target printer is a Canon SELPHY CP1000 connected to the Raspberry Pi and
configured through CUPS and Gutenprint.

Do not add a dedicated print-test page or print-test function.

The normal REVIEW print action is sufficient for physical validation.

# Validated target environment

The following target environment has already been validated manually:

- Raspberry Pi 5;
- CUPS command-line tools;
- Gutenprint 5.3.4;
- Canon SELPHY CP1000 detected through USB;
- CUPS printer queue created for the CP1000;
- physical JPEG printing confirmed.

The observed Gutenprint device URI was:

`gutenprint53+usb://canon-cp1000/<printer-serial>`

The observed CUPS model was:

`gutenprint.5.3://canon-cp1000/expert`

Do not hard-code the device URI or printer serial in application code.

The application must use the configured CUPS queue name.

# Validated baseline print profile

Use the following values as the default CP1000 print profile:

- page size: `Postcard`;
- color model: `RGB`;
- resolution: `300dpi`;
- image type: `Photo`;
- borderless: `True`;
- page-fit behavior: `Shrink`;
- color precision: `Normal`;
- color correction: `None`;
- legacy dye-sub gamma: `False`;
- brightness: neutral/default;
- contrast: neutral/default;
- saturation: neutral/default;
- gamma: neutral/default.

`Shrink` is the preferred page-fit behavior based on physical print testing.

These values are defaults, not hard-coded requirements.

They must remain configurable through the existing typed configuration and
administration architecture.

# Existing functionality to preserve

The application already provides:

- `PrinterBackend`;
- `NullPrinterBackend`;
- REVIEW print action;
- duplicate-action protection patterns;
- typed configuration;
- administration interface;
- photo gallery;
- opaque photo identifiers;
- application-controlled photo paths;
- participant status and error presentation.

Do not reimplement these features.

Do not modify capture, camera, QR, slideshow or participant navigation unless
a concrete printing integration defect requires a minimal correction.

The existing `NullPrinterBackend` must remain available for development on
machines without CUPS.

# Sources

Before editing, inspect:

- the existing `PrinterBackend` contract;
- `NullPrinterBackend`;
- REVIEW print route and service;
- photo and gallery models;
- application configuration;
- Admin > Printing;
- current duplicate-action protection;
- diagnostics service;
- applicable repository instructions;
- output of `lpoptions -p <configured-queue> -l` if it is documented in the
  repository.

Also inspect the installed command behavior where available:

- `lp`;
- `lpstat`;
- `lpoptions`;
- `cancel`.

Do not infer unsupported options from printer documentation when the installed
CUPS queue can provide the actual values.

# PrinterBackend contract

Implement `CupsPrinterBackend` behind the existing `PrinterBackend` contract.

Do not expose through the application-level contract:

- raw subprocess objects;
- raw CUPS output;
- shell command strings;
- Gutenprint-specific implementation objects.

If the existing contract is insufficient:

1. explain the concrete incompatibility;
2. make the smallest coherent change;
3. update `NullPrinterBackend`;
4. update application services and tests;
5. preserve hardware independence.

# CUPS command-line strategy

Use the system CUPS command-line interface for version 1:

- `lp` for job submission;
- `lpstat` for printer and job status;
- `lpoptions` for installed queue capabilities where required;
- `cancel` only for an explicit administrative cancellation action already
  supported by the application.

Do not add `pycups`.

Do not add another printing library.

Use Python standard-library subprocess APIs.

Never use:

`shell=True`

Every command must be represented as an argument list.

# Process execution boundary

Create or reuse a small typed process-execution boundary suitable for
deterministic tests.

The boundary must support:

- finite command execution;
- timeout;
- exit code;
- bounded standard output;
- bounded standard error;
- missing executable handling.

Do not create a general-purpose process framework.

Reuse an existing typed process runner if the camera integration already
provides one and it can be shared without coupling printing to camera-specific
behavior.

# Printer discovery

Implement the operations needed to obtain available CUPS queues.

Printer discovery must use CUPS commands rather than hard-coded printer names.

The application should be able to distinguish:

- CUPS command unavailable;
- CUPS service unavailable;
- no configured printer queues;
- configured queue not found;
- configured queue disabled;
- configured queue available.

Do not assume that every discovered printer is a Canon SELPHY CP1000.

# Queue validation

Before submitting a job, validate the configured queue against the queues
reported by CUPS.

The queue name must be treated as a validated value.

Do not allow a queue name to introduce additional command-line arguments.

Do not construct a shell command from the queue name.

If the configured queue does not exist, return a typed printing-domain error
and preserve the REVIEW page in a recoverable state.

# Print settings model

Create or extend a typed print-settings model.

Do not represent application-level settings as:

`dict[str, Any]`

The settings model must cover at least:

## General

- enabled/disabled printing;
- printer backend;
- CUPS queue name.

## Page and output

- page size;
- color model;
- resolution;
- image type;
- borderless;
- page-fit behavior;
- color precision;
- color correction;
- legacy dye-sub gamma.

## Adjustable color rendering

- brightness;
- contrast;
- saturation;
- gamma.

Do not expose advanced individual channel controls such as:

- cyan balance;
- magenta balance;
- yellow balance;
- fine cyan adjustment;
- fine magenta adjustment;
- fine yellow adjustment.

Do not implement expert color tuning in this milestone.

# CUPS option mapping

Map typed settings explicitly to allowlisted CUPS/Gutenprint options.

The target mapping is conceptually:

- page size -> `PageSize`;
- color model -> `ColorModel`;
- resolution -> `Resolution`;
- image type -> `StpImageType`;
- borderless -> `StpBorderless`;
- page-fit behavior -> `StpiShrinkOutput`;
- color precision -> `StpColorPrecision`;
- color correction -> `StpColorCorrection`;
- legacy dye-sub gamma -> `StpLegacyDyesubGamma`;
- brightness -> `StpBrightness`;
- contrast -> `StpContrast`;
- saturation -> `StpSaturation`;
- gamma -> `StpGamma`.

Use only option names and values confirmed by the configured queue where the
existing architecture supports capability checking.

Do not accept arbitrary CUPS options from:

- HTTP requests;
- admin forms;
- JSON configuration;
- query parameters.

# Neutral color values

The Gutenprint queue represents neutral color-tuning values using `None`.

In the application model, represent neutral/default values clearly and
type-safely.

Do not confuse:

- Python `None`, meaning no override configured;
- the literal Gutenprint option value `None`.

The command builder must deliberately decide whether to:

- omit a neutral option;
- or emit the exact driver value `None`.

Use the behavior confirmed by the configured queue and document the choice.

# Allowed values

Use constrained typed values for enum-like settings.

For the validated Canon CP1000 profile, expected values include:

## Page size

- `Postcard`;
- other queue-reported values only if intentionally supported.

## Color model

- `RGB`;
- optionally other queue-reported values if required later.

Use `RGB` as the default.

## Resolution

- `300dpi`.

## Image type

At minimum:

- `Photo`.

Use `Photo` as the default.

## Borderless

- `False`;
- `True`.

Use `True` as the default.

## Page-fit behavior

- `Shrink`;
- `Crop`;
- `Expand`.

Use `Shrink` as the default.

## Color precision

- `Normal`;
- `Best`.

Use `Normal` as the default.

## Color correction

Support the useful queue-reported choices, including at minimum:

- `None`;
- `Accurate`;
- `Bright`;
- `Hue`;
- `Uncorrected`;
- `Desaturated`.

Do not expose modes that the installed queue does not report.

Use `None` as the default.

## Legacy dye-sub gamma

- `False`;
- `True`.

Use `False` as the default.

# Brightness, contrast, saturation and gamma

Expose only these four advanced color-tuning controls:

- brightness;
- contrast;
- saturation;
- gamma.

Use the exact values supported by the configured Gutenprint queue.

Prefer select controls populated from validated supported values when the
driver exposes discrete choices.

Do not expose a completely free numeric input if the installed driver accepts a
specific discrete set plus `Custom.REAL`.

Do not implement `Custom.REAL` unless the existing CUPS invocation behavior and
value format have been explicitly validated.

For version 1, it is acceptable to support:

- neutral/default;
- the discrete values advertised by the queue.

Default all four settings to neutral.

# Capability handling

Where practical, query the configured queue with `lpoptions` and verify that
the required options exist.

Do not execute `lpoptions` for every participant page render.

Capability discovery may occur:

- during backend initialization;
- on an explicit protected diagnostics/admin operation;
- through a bounded cache with a clear refresh strategy.

Keep the implementation simple.

If a configured option is no longer supported by the selected queue:

- do not submit it blindly;
- report it as unsupported;
- preserve the remaining valid settings;
- provide a useful admin error or warning.

# Job submission

Submit the original managed JPEG using `lp`.

The conceptual command is:

`lp -d <queue> -o <option>=<value> ... <photo-path>`

The actual command must be an argument list.

Before submission:

1. validate that printing is enabled;
2. validate the queue;
3. resolve the photo through GalleryService;
4. verify that the file exists;
5. verify that it is a managed printable JPEG;
6. validate print settings;
7. construct the allowlisted `lp` argument list.

Do not accept a filesystem path directly from the browser.

# Job identifier

Parse the CUPS job identifier returned by `lp`.

Return a typed `PrintResult` containing at least:

- printer queue;
- job identifier;
- submission status;
- submission timestamp if already part of the domain model;
- useful non-sensitive status text.

Treat unexpected `lp` output as a controlled parsing error.

Do not mark a job as physically printed merely because CUPS accepted it.

Distinguish:

- submitted to CUPS;
- queued;
- completed according to available CUPS status;
- failed;
- cancelled;
- physical output not independently confirmed.

# Duplicate print prevention

Prevent accidental duplicate printing caused by:

- repeated taps;
- browser retries;
- page refresh;
- repeated POST submission.

Use an idempotency key or equivalent application-level mechanism associated
with the photo and print action.

The browser should disable the print action while submission is running, but
server-side duplicate protection remains mandatory.

A duplicate request must not submit a second CUPS job silently.

Document when a user is allowed to intentionally print the same photo again.

If intentional reprinting is already supported, it must require a new explicit
action or new operation identifier.

# Timeout and failures

Use explicit timeouts for all CUPS command executions.

Translate failures into typed printing-domain exceptions.

Handle at least:

- `lp` unavailable;
- `lpstat` unavailable;
- `lpoptions` unavailable where required;
- CUPS unavailable;
- no queues;
- configured queue missing;
- queue disabled;
- photo missing;
- invalid photo;
- job submission timeout;
- non-zero exit;
- job-ID parsing failure;
- unsupported configured option.

Do not expose raw subprocess stderr to participants.

Store a bounded diagnostic representation for logs and protected admin
diagnostics.

# REVIEW integration

Preserve the existing REVIEW print action.

When printing is available:

1. the participant taps `Imprimer`;
2. the button becomes disabled while submission is pending;
3. the server validates and submits the job;
4. the participant remains on REVIEW;
5. the UI reports that the photo was submitted to the printer;
6. duplicate submission is blocked.

Do not state that the physical photo is ready merely because the job was
accepted by CUPS.

Use participant-facing wording conceptually equivalent to:

`Photo envoyée à l'imprimante`

On failure, show a concise recoverable message.

Do not expose technical CUPS details on the participant screen.

When `NullPrinterBackend` is active, preserve the existing development
behavior.

# Admin > Printing

Extend the existing administration interface with a clear Printing section.

Do not create a separate administration page unless the current admin
architecture already uses separate sections/pages.

Expose at least:

## Printer

- printing enabled;
- printer backend;
- CUPS queue name;
- detected/configured queue status.

## Paper and layout

- page size;
- borderless;
- page-fit behavior;
- image type;
- resolution.

## Color

- color model;
- color precision;
- color correction;
- legacy dye-sub gamma.

## Color adjustment

- brightness;
- contrast;
- saturation;
- gamma.

Do not expose:

- cyan adjustment;
- magenta adjustment;
- yellow adjustment;
- individual channel gamma controls;
- fine color controls;
- arbitrary CUPS arguments.

# Admin controls

Use typed and constrained controls:

- select for queue name;
- select for enum-like CUPS values;
- checkbox for booleans;
- select for discrete Gutenprint adjustment values.

Display neutral/default values clearly.

For example:

`Par défaut / neutre`

Do not display the internal Gutenprint literal `None` without a user-friendly
label if that would be confusing.

Persist stable driver values, not translated display labels.

# Admin validation

Validate all print settings server-side.

When settings are saved:

1. validate general configuration;
2. validate queue name;
3. validate allowlisted option values;
4. persist atomically using the existing configuration system;
5. report unsupported options clearly;
6. do not submit a print job.

There is no print-test function in this milestone.

Physical validation continues through the normal REVIEW print action.

# Admin diagnostics

Expose safe printing diagnostics such as:

- `lp` availability;
- `lpstat` availability;
- configured queue;
- queue status;
- detected model/description where available;
- currently effective print profile;
- most recent submitted job identifier;
- most recent known job status;
- last submission error in sanitized form.

Do not expose:

- full raw subprocess output;
- arbitrary environment variables;
- unrelated filesystem paths;
- USB serial unless it is already intentionally part of protected diagnostics.

If the effective command is displayed, sanitize the photo path where
appropriate and present it for diagnosis only.

# Configuration and backward compatibility

Use the existing typed configuration and atomic persistence architecture.

Existing configuration files without the new print settings must continue to
load using the documented defaults.

Do not overwrite or reject older valid configuration solely because new fields
are absent.

Do not store raw `lp` command fragments.

Do not store arbitrary `-o` options.

# Logging

Log useful events including:

- printer discovery;
- queue validation;
- job submission start;
- job identifier returned;
- duplicate request rejected;
- timeout;
- submission failure;
- status update failure.

Log the effective argument list in a safe readable form where useful for
diagnosis.

Execute the original argument list with `shell=False`.

Do not log image data.

# Toolchain

Prefer the system CUPS command-line interface:

- `lp`;
- `lpstat`;
- `lpoptions`;
- `cancel` only for explicit supported cancellation.

Do not add `pycups`.

Do not add Python dependencies.

Do not add:

- shell command execution;
- printing frameworks;
- frontend frameworks;
- linting tools;
- formatting tools.

Do not change:

- `uv_build`;
- application deployment architecture;
- existing frontend toolchain.

Do not install or configure CUPS automatically.

The operating-system CUPS and Gutenprint setup must remain an explicit system
prerequisite.

# Documentation

Follow repository-wide typing and documentation requirements.

Document:

- `CupsPrinterBackend` responsibility;
- differences from `NullPrinterBackend`;
- queue discovery;
- queue validation;
- CUPS capability discovery;
- print-setting validation;
- safe option mapping;
- job submission;
- job-ID parsing;
- job-status semantics;
- duplicate prevention;
- timeout behavior;
- unavailable-CUPS behavior;
- neutral color values;
- requested versus effective CUPS options;
- physical-output limitations.

Update existing architecture, configuration and troubleshooting documentation
where relevant.

Replace any obsolete Canon SELPHY CP740 assumptions with the actual target:

`Canon SELPHY CP1000`

Do not claim that CUPS job completion independently proves successful physical
output.

# Tests

Use a typed process-runner fake or mock.

All automated tests must run without:

- CUPS;
- Gutenprint;
- printer hardware;
- Raspberry Pi;
- Internet access.

Add or update pytest tests covering at least:

## Discovery and queue validation

- CUPS commands unavailable;
- CUPS service unavailable;
- no printers;
- configured queue found;
- configured queue missing;
- disabled queue;
- safe queue name;
- unsafe queue value rejected.

## Option mapping

- default CP1000 profile;
- Postcard page size;
- RGB color model;
- 300dpi;
- Photo image type;
- borderless True;
- Shrink page-fit mode;
- Normal color precision;
- None color correction;
- legacy dye-sub gamma False;
- neutral brightness;
- neutral contrast;
- neutral saturation;
- neutral gamma;
- non-default valid values;
- unsupported values rejected;
- arbitrary CUPS option rejected.

## Admin

- existing configuration loads with defaults;
- valid settings persist;
- invalid settings do not persist;
- safe queue selection;
- queue status displayed;
- only brightness, contrast, saturation and gamma exposed for advanced tuning;
- CMY and fine-adjustment controls absent;
- no print-test action exposed.

## Job submission

- successful submission;
- expected command argument list;
- `shell=True` never used;
- valid job ID parsed;
- unexpected submission output;
- non-zero exit;
- command timeout;
- missing photo;
- invalid photo;
- unsupported option;
- bounded error diagnostics.

## Duplicate prevention

- repeated request with same idempotency identity;
- duplicate does not create another process call;
- explicit later reprint behavior where supported;
- idempotency state released or persisted according to the chosen design.

## Status

- queued status parsing;
- completed status parsing where available;
- failed status;
- cancelled status;
- unknown status;
- printer unavailable after submission.

## Regression

- `NullPrinterBackend` remains functional;
- REVIEW remains on the same photo after submission;
- existing capture and gallery tests continue to pass;
- no CUPS invocation occurs when NullPrinterBackend is active.

# Automated validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

The complete automated suite must remain hardware-independent and runnable on
the Windows development laptop.

# Real Raspberry Pi validation

After automated validation passes, validate the real integration on the
Raspberry Pi.

Use:

- configured CUPS queue for Canon SELPHY CP1000;
- existing Gutenprint driver;
- normal REVIEW print action;
- a real managed JPEG from the photobooth.

Validate:

1. Admin detects or validates the queue;
2. Admin displays the effective default profile;
3. save the default print settings;
4. open a captured photo in REVIEW;
5. submit one print;
6. verify a CUPS job identifier is returned;
7. verify the participant remains on REVIEW;
8. verify duplicate tapping does not create another CUPS job;
9. verify the photo is physically printed;
10. verify the result uses Postcard, Photo, Borderless and Shrink;
11. change one safe color setting in Admin;
12. submit another normal REVIEW print only if physical validation is needed;
13. restore the neutral value;
14. stop the application;
15. verify no application-owned process remains.

Do not add a special print-test workflow for this validation.

Use the normal participant printing path.

# Expected result

Before editing:

1. confirm the current workspace platform;
2. inspect the existing PrinterBackend and REVIEW print flow;
3. inspect the current configuration and Admin > Printing;
4. inspect the local CUPS queue/options when running on the Raspberry Pi;
5. describe the typed print-settings model;
6. describe the CUPS option mapping;
7. describe duplicate-prevention behavior;
8. list files expected to change.

Then implement the milestone.

After implementation report only:

## Files changed

List repository files changed.

## Backend design

Summarize:

- process boundary;
- discovery;
- queue validation;
- submission;
- job ID and status;
- duplicate prevention.

## Print settings

List:

- application setting;
- default;
- allowed values;
- emitted CUPS option.

## Admin

List the Printing sections and controls added.

Confirm explicitly:

- no print-test page/function was added;
- no CMY or fine-channel controls were added.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform.

## Real printer validation

For each item report PASS, FAIL or SKIP:

- queue validation;
- job submission;
- job ID;
- duplicate prevention;
- participant feedback;
- physical print;
- default CP1000 profile;
- application shutdown.

## Limitations

List only behavior not actually validated.

## Readiness

Conclude with exactly one of:

- `CUPS PRINTING READY`
- `CUPS PRINTING NOT READY`

If not ready, list the blocking failures.

Stop after CUPS printing integration.

Do not implement:

- print-test page;
- print-test action;
- cyan/magenta/yellow tuning;
- fine color adjustment controls;
- printer setup or driver installation;
- CUPS queue creation;
- new participant workflows;
- unrelated UI redesign.