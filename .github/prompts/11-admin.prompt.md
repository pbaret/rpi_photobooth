---
agent: agent
description: Add protected administration and runtime booth configuration
---

# Goal

Implement the local administration interface for the photobooth.

At the end of this milestone, an administrator must be able to:

1. open `/admin`;
2. authenticate using the configured administrator secret;
3. view the current booth configuration;
4. modify supported runtime settings;
5. validate and persist those settings;
6. understand whether a changed setting is immediately active or requires a
   camera restart;
7. view basic operational diagnostics;
8. return to the booth.

Do not implement a user/account system.

# Context

The application already provides:

- typed configuration;
- atomic JSON configuration persistence;
- Synthetic and OpenCV camera backends;
- booth preview;
- capture workflow;
- gallery and review;
- QR download;
- slideshow.

Administration is intended for a trusted local network.

The administrator interface provides lightweight protection against normal
booth users accessing settings.

It is not intended to provide Internet-facing authentication.

The administrator secret is startup/deployment configuration and must not be
stored in the runtime-editable JSON configuration.

# Sources

Before editing, inspect only the relevant:

- configuration models and persistence;
- application factory;
- existing camera backend interface;
- booth configuration usage;
- existing templates and CSS;
- diagnostics already available;
- `docs/configuration.md`;
- applicable repository instructions.

Reuse existing configuration models and validation.

Do not create a second configuration system specifically for the admin UI.

# Authentication

Protect administration routes using the configured administrator secret.

The secret must:

- come from startup/deployment configuration;
- not be committed to the repository;
- not be written to runtime JSON configuration;
- not appear in logs;
- not appear in diagnostics;
- not be returned to the browser after authentication.

Use standard-library secure secret comparison where applicable.

Keep authentication deliberately simple.

Do not add:

- user accounts;
- registration;
- password recovery;
- OAuth;
- an authentication framework;
- a database.

# Administration page

Create the administration interface under:

`/admin`

Organize the settings into clear sections.

At minimum expose the settings already implemented and meaningful for the
current application.

## Booth

Include relevant existing settings such as:

- booth name;
- countdown duration;
- inactivity timeout;
- slideshow enabled;
- slideshow interval.

## Network and download

Include:

- `public_base_url`;
- download-token expiration where currently configurable.

## Camera

Expose the camera settings already supported by the current configuration and
backend architecture, such as:

- selected backend if runtime editing of it is already supported;
- webcam index;
- preview resolution;
- capture resolution;
- preview mirroring;
- JPEG quality.

Do not invent backend capabilities in this milestone.

The advanced capability-driven camera settings UI belongs to the next
camera-settings milestone.

## Printing

Expose only printing configuration already supported by the current model.

Do not implement CUPS yet.

## Diagnostics

Display useful non-sensitive information such as:

- configured camera backend;
- camera availability/status already exposed by the backend;
- number of managed photos;
- available storage if an existing service can provide it cleanly;
- configured public base URL;
- printer backend/status already available;
- last capture status if already tracked.

Do not add substantial infrastructure solely to produce a diagnostic field.

Do not expose:

- administrator secret;
- download tokens;
- raw subprocess output;
- unnecessary filesystem paths;
- environment variables.

# Configuration update

Configuration changes must use POST.

Validate every submitted value server-side using the existing configuration
validation model.

Do not rely solely on HTML input constraints.

If validation fails:

- do not persist a partial configuration;
- preserve the previously valid configuration;
- display useful field-level or section-level feedback;
- preserve safe submitted values where practical.

If validation succeeds:

1. create the validated new configuration;
2. persist it using the existing atomic configuration mechanism;
3. apply settings that can safely take effect immediately;
4. clearly report settings requiring a lifecycle restart.

Do not create a second persistence implementation in the admin routes.

# Runtime application behavior

Distinguish between:

- persisted configuration;
- currently effective configuration.

A successful save must not falsely claim that a setting is active if the
required component has not applied it yet.

For settings that can be applied immediately, update the relevant application
behavior.

For settings requiring camera restart, use the smallest safe existing
lifecycle mechanism if one is already available.

If automatic camera restart is not yet safely supported, persist the value and
clearly report that a restart is required instead of implementing an unsafe
shortcut.

# Navigation

Administration is a dedicated page.

Expected navigation:

`booth -> admin -> booth`

Returning to the booth must restore normal booth behavior.

Administrative actions must not accidentally trigger:

- capture;
- slideshow wake-up behavior;
- photo deletion;
- printing.

# Functional UI

Build a functional touch-friendly administration interface using only:

- Flask/Jinja;
- HTML;
- CSS;
- vanilla JavaScript where needed.

Group settings logically.

Use appropriate native controls:

- number inputs for bounded numeric values;
- checkboxes for booleans;
- selects for enums;
- URL/text inputs where appropriate.

Display:

- current values;
- validation errors;
- save result;
- restart-required information.

Do not spend effort on final visual branding.

# Toolchain

Do not add:

- account-management framework;
- Flask-WTF or another form framework;
- database;
- frontend framework;
- authentication framework.

Use the existing Flask, Jinja2 and standard-library functionality.

Do not add a runtime dependency unless a concrete requirement cannot be met
with the current stack.

# Documentation

Follow repository-wide typing and documentation requirements.

In particular document:

- authentication scope and limitations;
- secret ownership;
- configuration validation flow;
- persistence behavior;
- persisted versus effective settings;
- settings applied immediately;
- settings requiring restart;
- diagnostics security boundary.

# Tests

Add or update pytest tests covering at least:

- unauthenticated admin access;
- valid authentication;
- invalid authentication;
- absent administrator secret;
- administrator secret not persisted in runtime configuration;
- valid configuration update;
- invalid configuration value;
- previous configuration preserved after invalid update;
- atomic configuration persistence;
- immediately applicable setting;
- restart-required setting;
- state-changing operation rejected through GET where applicable;
- diagnostics containing expected safe values;
- diagnostics not containing secrets.

Reuse existing application/test fixtures.

Do not require physical hardware.

# Validation

Execute:

`uv run pyright`

and the relevant pytest tests.

Run the complete pytest suite because this milestone modifies configuration
used by several existing workflows.

# Manual validation

Provide a concise manual validation procedure:

1. start the application with an administrator secret;
2. open the booth and verify normal operation;
3. open `/admin`;
4. verify authentication protection;
5. authenticate;
6. change the countdown value;
7. save;
8. return to the booth;
9. verify the new countdown is actually used;
10. change a camera-related setting;
11. verify whether it is immediately applied or correctly reported as requiring
    restart;
12. inspect diagnostics;
13. restart the application and verify persisted settings remain;
14. verify the administrator secret does not appear in the persisted JSON.

# Expected result

Before editing:

1. inspect the existing configuration and application lifecycle;
2. identify which current settings can apply immediately;
3. identify which current settings require restart;
4. identify which safe diagnostics already exist;
5. list the files expected to change.

After implementation report only:

- files changed;
- admin sections implemented;
- authentication mechanism;
- settings applied immediately;
- settings requiring restart;
- diagnostics exposed;
- Pyright result;
- pytest result;
- manual validation procedure.

Stop after this milestone.

Do not implement:

- advanced camera capability discovery;
- new Camera Module 3 controls;
- rpicam integration;
- CUPS;
- account management;
- final visual branding.