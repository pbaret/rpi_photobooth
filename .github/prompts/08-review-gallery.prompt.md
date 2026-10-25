---
agent: agent
description: Implement the local photo gallery and review workflow
---

# Goal

Implement persistent local photo management and the review screen displayed
after a successful capture.

At the end of this milestone, the complete development workflow must be usable:

IDLE
  -> COUNTDOWN
  -> CAPTURING
  -> REVIEW
  -> return to IDLE

The review screen must display the captured photo and provide functional
actions for:

- retake;
- delete;
- print placeholder.

QR download is intentionally deferred to the next milestone.

# Context

The previous milestone implemented the capture workflow.

A successful capture already produces a photo identified by an opaque
application-controlled photo ID.

This milestone turns captured files into managed gallery items and introduces
the dedicated review page.

The application uses:

- local filesystem storage;
- JSON metadata;
- Pillow for image validation and thumbnail generation;
- NullPrinterBackend for development printing behavior.

Do not introduce a database.

# Sources

Before editing, inspect only the relevant files:

- `docs/architecture.md`;
- `docs/configuration.md`;
- the existing capture workflow;
- existing photo/domain models;
- existing services;
- existing booth routes;
- existing templates and frontend files;
- applicable repository instructions.

Preserve the architecture established in previous milestones.

# GalleryService

Implement or complete `GalleryService`.

GalleryService owns the application-level management of captured photos.

It must provide the operations required to:

- register a successfully captured photo;
- retrieve a photo by opaque photo ID;
- list managed photos where required;
- delete a photo;
- generate and resolve thumbnails;
- expose the metadata needed by the review page.

HTTP routes must not manipulate photo files directly.

# Photo identity

Continue using opaque, unpredictable application-generated photo IDs.

Never use a client-provided filesystem path.

Never construct a filesystem path directly from an unvalidated HTTP
identifier.

Unknown photo IDs must produce a controlled not-found result.

Path traversal attempts must never access files outside the application-managed
photo storage.

# Metadata

Persist local photo metadata as JSON.

Do not introduce SQLite or another database.

Metadata must be owned by GalleryService or its dedicated storage component,
not by Flask routes.

Define a typed metadata model.

Store only information useful to the application.

Document:

- metadata ownership;
- serialization lifecycle;
- behavior when metadata is missing;
- behavior when metadata is malformed;
- consistency behavior after partial filesystem failure.

Do not expose internal filesystem paths through HTTP responses.

# Thumbnails

Generate a thumbnail for successfully managed photos using Pillow.

Thumbnails are intended for the future slideshow.

The thumbnail lifecycle must follow the original photo lifecycle.

When a photo is deleted, its thumbnail must not remain available as a valid
gallery item.

Do not generate slideshow behavior in this milestone.

# Review page

Add a dedicated review route using the opaque photo ID.

Conceptually:

`GET /review/<photo_id>`

The review page must:

- display the captured image prominently;
- identify the currently reviewed photo internally by its opaque ID;
- provide large touch-friendly actions;
- work in portrait and landscape;
- avoid requiring normal desktop browser controls.

Provide these actions:

- `Reprendre`;
- `Supprimer`;
- `Imprimer`.

Reserve a suitable area for the QR code that will be implemented in the next
milestone, but do not implement QR generation yet.

# Retake

Retake must:

1. use a state-changing POST operation;
2. leave the existing photo intact;
3. return the application to the booth;
4. restore the ready/preview state;
5. allow the user to start a new capture.

Do not automatically start a new countdown.

Do not implicitly delete the previous photo.

# Delete

Delete must:

1. require explicit user confirmation in the UI;
2. use POST;
3. resolve the photo through GalleryService;
4. delete or invalidate the managed photo;
5. ensure the photo is no longer accessible through application media routes;
6. clean up its thumbnail;
7. return the user to the booth in ready state.

Repeated deletion must produce controlled behavior and must not expose internal
filesystem errors.

# Print placeholder

Connect the review `Imprimer` action to the existing PrinterBackend
abstraction.

On the development computer, use NullPrinterBackend.

Do not implement CUPS in this milestone.

The print action must:

- use POST;
- not leave the review page after a successful placeholder operation;
- return a clear user-visible status;
- not submit duplicate print operations due to repeated button presses.

If PrinterBackend is not yet sufficiently defined for this operation, make the
smallest coherent contract addition required by this milestone.

Do not implement future CUPS-specific behavior.

# Navigation

The navigation after this milestone must behave as follows:

Successful capture:

`booth -> review/<photo_id>`

Retake:

`review/<photo_id> -> booth`

Delete:

`review/<photo_id> -> booth`

Print:

`review/<photo_id> -> review/<photo_id>`

Returning to the booth must restore the camera preview and IDLE state.

Use Post/Redirect/Get where appropriate to avoid accidental repeated
state-changing operations.

# Functional UI

This milestone includes the functional review UI.

Use only:

- Flask/Jinja;
- HTML;
- CSS;
- vanilla JavaScript.

Do not add frontend dependencies.

Do not perform final visual branding.

The goal is a functional touch-first photobooth interface, not final visual
polish.

Touch actions must be clearly identifiable and large enough for use from a
smartphone or kiosk-style display.

# Toolchain

Do not add a database dependency.

Use:

- pathlib;
- JSON metadata;
- Pillow already installed.

Do not add a new runtime dependency unless a concrete requirement cannot be
satisfied by the existing project stack.

# Documentation

Follow repository-wide documentation requirements.

In particular, document:

- photo identity;
- GalleryService ownership;
- metadata ownership;
- metadata persistence;
- thumbnail lifecycle;
- deletion semantics;
- retake semantics;
- print placeholder semantics;
- consistency behavior after partial filesystem failure.

All Python APIs introduced or modified must be fully typed.

# Tests

Add or update pytest tests covering at least:

- registering a captured photo;
- review of an existing photo;
- unknown photo ID;
- path traversal attempt;
- metadata persistence;
- malformed metadata;
- thumbnail generation;
- corrupt source image;
- successful deletion;
- repeated deletion;
- thumbnail cleanup after deletion;
- media unavailable after deletion;
- retake without implicit deletion;
- retake returning the workflow to ready state;
- NullPrinterBackend print action;
- relevant review routes and HTTP methods.

Tests must use temporary directories.

Tests must not require:

- a physical webcam;
- Raspberry Pi hardware;
- CUPS;
- a printer.

# Validation

Execute:

`uv run pyright`

and the relevant pytest tests.

Then run the complete pytest suite because this milestone connects capture,
gallery, routes and UI workflow.

If validation fails because of this milestone, fix the issue and rerun the
relevant checks.

# Manual validation

Provide a concise manual test using the OpenCV backend:

1. open the booth;
2. verify live preview;
3. take a photo;
4. complete the countdown;
5. arrive on the review page;
6. verify that the captured photo is displayed;
7. test print placeholder and remain on review;
8. test retake and verify preview returns;
9. capture another photo;
10. delete it and verify return to the booth.

# Expected result

Before editing:

1. inspect the existing capture, storage and route implementation;
2. briefly describe how captured photos are currently stored;
3. propose the smallest GalleryService design supporting this milestone;
4. list files expected to change.

After implementation report only:

- files changed;
- GalleryService operations introduced;
- review actions implemented;
- metadata approach;
- Pyright result;
- pytest result;
- manual validation procedure;
- behavior deliberately deferred to the QR and CUPS milestones.

Stop after this milestone.

Do not implement:

- QR code generation;
- download tokens;
- slideshow;
- CUPS;
- administration;
- final visual branding.