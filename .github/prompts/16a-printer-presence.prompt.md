---
agent: agent
description: Prevent print submission when the physical CP1000 is unavailable
---

# Goal

Add a physical-printer availability check to CupsPrinterBackend.

When CupsPrinterBackend is selected, the application must distinguish between:

1. a configured CUPS queue;
2. the physical Canon SELPHY CP1000 actually being connected and powered on.

If the configured CP1000 is not physically detected:

- printing must be considered unavailable;
- no CUPS print job must be submitted;
- nothing must be added to the CUPS queue;
- the participant must receive the existing printer-unavailable experience,
  similar to the behavior already used with NullPrinterBackend;
- the admin diagnostics must clearly report that the configured queue exists
  but the physical printer is unavailable.

Do not change printer behavior when NullPrinterBackend is selected.

# Context

The application already provides:

- PrinterBackend;
- NullPrinterBackend;
- CupsPrinterBackend;
- configured CUPS queue validation;
- CUPS job submission;
- print status;
- duplicate-print prevention;
- REVIEW print action;
- Admin > Printing.

The target production printer is:

Canon SELPHY CP1000

connected through USB to the Raspberry Pi.

The current system configuration has already demonstrated that the physical
printer appears through `lsusb` when connected and powered on.

A persistent CUPS queue is not sufficient evidence that the physical printer
is currently available.

# Sources

Before editing, inspect:

- PrinterBackend;
- CupsPrinterBackend;
- NullPrinterBackend;
- PrinterStatus or equivalent domain model;
- printing service;
- REVIEW print behavior;
- Admin printing diagnostics;
- existing process-runner abstraction;
- existing CUPS availability checks;
- applicable repository instructions.

Reuse existing printer-unavailable domain behavior where possible.

Do not create a second printing-status architecture.

# Physical USB presence

When CupsPrinterBackend is active, add an explicit physical-presence check for
the target USB printer.

Use the system `lsusb` command through the existing typed process-execution
boundary.

Do not use:

- shell pipelines;
- `grep` through `shell=True`;
- arbitrary shell commands.

Execute `lsusb` as an argument list and parse its bounded output in Python.

# Printer identification

Do not identify availability solely by checking that any Canon USB device is
present.

Use the most stable CP1000 identification information available from the
actual system diagnostics.

Prefer a deterministic identification strategy based on information exposed
by `lsusb`, such as the validated USB vendor/product identity, if available.

Do not hard-code the printer USB serial number unless the existing application
configuration explicitly requires locking the booth to one individual physical
printer.

The intended default behavior is:

Canon SELPHY CP1000 model present
    -> physically available

CP1000 model absent
    -> physically unavailable

Document the selected identification strategy.

# Availability sequence

Before a print job is submitted with CupsPrinterBackend, validate in this
order:

1. required CUPS commands are available;
2. configured CUPS queue exists;
3. configured queue is usable according to existing backend logic;
4. physical CP1000 is detected through USB;
5. only then construct and execute the `lp` submission.

If physical presence fails, stop before `lp`.

Do not add the job to CUPS and hope that it eventually prints when the printer
is connected later.

This behavior is intentional for photobooth use.

# Missing or powered-off printer

When the CP1000 is:

- unplugged;
- powered off;
- otherwise absent from USB discovery;

CupsPrinterBackend must report a typed unavailable-printer result.

Reuse the existing printer availability/error model if it can represent this
condition cleanly.

Do not expose `lsusb` output to participant-facing pages.

The participant-facing behavior should be conceptually similar to the existing
printer-unavailable behavior.

For example:

`Imprimante indisponible`

Keep the participant on the existing REVIEW page.

Do not enqueue a job.

# Admin diagnostics

Admin > Printing should distinguish at least:

- CUPS available;
- configured queue found;
- physical printer detected.

For example conceptually:

CUPS
    Available

Queue
    Canon_CP1000
    Available

Physical printer
    Canon SELPHY CP1000
    Connected

or:

Physical printer
    Canon SELPHY CP1000
    Not detected

Do not confuse queue availability with physical presence.

Do not expose unnecessary raw USB descriptors.

# lsusb unavailable

If the `lsusb` executable itself is unavailable:

- do not silently assume that the printer is present;
- report physical-printer detection as unavailable/unknown;
- do not submit a production print job unless the existing architecture has a
  deliberate fallback policy.

For the Raspberry Pi production environment, `lsusb` availability should be
treated as a printer-backend prerequisite.

Do not install system packages automatically.

# Scope of this check

This milestone detects only physical USB presence.

It must not claim to detect:

- paper availability;
- ink/dye/ribbon availability;
- paper jam;
- consumable level;
- successful physical printing.

A printer appearing in `lsusb` means only that the expected USB device is
currently visible to the Raspberry Pi.

Document this limitation.

# Paper and consumable status

Do not implement speculative paper-out or consumable-status detection.

The actual Canon SELPHY CP1000 + Gutenprint + CUPS combination has not yet been
validated for reliable paper/consumable status reporting.

Preserve any existing CUPS job/status information, but do not translate an
unknown CUPS state into a specific `paper empty` condition without observed
evidence from the real printer.

Leave room in the existing typed printer-status model for future specific
failure reasons if real hardware testing later demonstrates reliable signals.

# Process execution

Use the existing process runner where possible.

Do not introduce another subprocess abstraction solely for `lsusb`.

Never use:

`shell=True`

Use explicit timeout and bounded output.

Translate:

- executable missing;
- timeout;
- malformed/unexpected output

into appropriate internal diagnostic states.

# Performance

Do not continuously poll `lsusb` from participant pages.

Physical presence must be checked:

- immediately before print submission;

and may additionally be queried:

- when Admin > Printing diagnostics are explicitly requested.

Do not run `lsusb` continuously in a background loop.

# Logging

Log useful availability events such as:

- physical CP1000 detected;
- physical CP1000 missing;
- `lsusb` unavailable;
- physical check timeout.

Do not log excessive raw USB output.

# Toolchain

Do not add Python dependencies.

Use:

- existing typed process runner;
- standard-library parsing;
- system-provided `lsusb`.

Do not add:

- pyusb;
- pycups;
- USB Python libraries;
- background polling;
- system services.

Do not modify the operating system automatically.

# Documentation

Follow repository-wide typing and documentation requirements.

Document:

- why a CUPS queue does not prove physical printer availability;
- USB presence check;
- selected CP1000 identification strategy;
- when the check runs;
- behavior when the printer is missing;
- distinction between physical presence and consumable readiness;
- limitation regarding paper/ribbon detection.

Update troubleshooting documentation where appropriate.

# Tests

Add or update pytest tests covering at least:

## USB detection

- CP1000 present;
- CP1000 absent;
- unrelated Canon USB device present;
- unrelated USB device present;
- multiple USB devices;
- `lsusb` unavailable;
- `lsusb` timeout;
- malformed/unexpected output.

## Print submission

- CupsPrinterBackend + queue available + CP1000 present -> submission allowed;
- queue available + CP1000 absent -> no `lp` execution;
- queue available + CP1000 powered-off simulation -> no `lp` execution;
- queue missing -> existing behavior preserved;
- NullPrinterBackend -> no `lsusb` requirement.

Assert explicitly that the process runner receives no `lp` invocation when
physical-printer presence fails.

## Participant behavior

- printer unavailable keeps REVIEW usable;
- no job identifier is created;
- existing printer-unavailable message/behavior is reused.

## Admin

- queue and physical presence reported independently;
- connected status;
- disconnected status;
- unknown physical-detection status.

# Validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

# Real Raspberry Pi validation

After automated tests pass, validate using the real Canon SELPHY CP1000.

## Printer connected and powered on

1. ensure CupsPrinterBackend is selected;
2. power on and connect the CP1000;
3. verify Admin reports the physical printer as detected;
4. print through the existing REVIEW action;
5. verify one CUPS job is submitted.

## Printer powered off

1. ensure the same CUPS queue remains configured;
2. power off the CP1000;
3. verify Admin shows the queue but not the physical printer;
4. attempt to print from REVIEW;
5. verify the participant receives the unavailable-printer behavior;
6. verify no new CUPS job is created.

## Printer unplugged

Repeat with the USB cable disconnected.

Verify again:

- physical printer not detected;
- no `lp` submission;
- no new CUPS job.

Do not modify CUPS configuration during these tests.

# Expected result

Before editing:

1. inspect current CupsPrinterBackend status checks;
2. inspect NullPrinterBackend unavailable behavior;
3. inspect real `lsusb` output with the CP1000 connected;
4. identify the stable USB model identifier to use;
5. describe where the physical check belongs in the print submission sequence;
6. list files expected to change.

Then implement the milestone.

After implementation report only:

## Detection strategy

State exactly how the CP1000 is identified.

## Behavior

Report the distinction between:

- queue available;
- physical printer available;
- physical printer unavailable.

## Files changed

List changed files.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform.

## Real hardware validation

Report PASS, FAIL or SKIP for:

- connected printer detected;
- powered-off printer rejected;
- unplugged printer rejected;
- no job queued while unavailable;
- normal print still succeeds when reconnected.

## Known limitation

State explicitly that physical USB presence does not prove paper or consumable
availability.

Stop after this milestone.

Do not implement:

- paper-level detection;
- consumable-level detection;
- printer polling loop;
- new participant workflow;
- unrelated printing functionality.