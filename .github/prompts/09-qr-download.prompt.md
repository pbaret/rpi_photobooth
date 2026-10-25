---
agent: agent
description: Add local photo download and QR code to the review workflow
---

# Goal

Add QR-based local photo download to the existing review screen.

At the end of this milestone:

1. a reviewed photo displays a QR code;
2. a smartphone on the same LAN can scan it;
3. the QR URL opens the photobooth;
4. the corresponding full-resolution photo can be downloaded;
5. an expired, revoked or deleted-photo token no longer provides access.

Do not implement any cloud upload or external sharing service.

# Context

The previous milestone provides:

- managed photos through GalleryService;
- opaque photo IDs;
- persisted photo metadata;
- a review page;
- photo deletion.

This milestone extends that existing workflow.

The QR code must identify a temporary application download capability, not a
filesystem path and not the photo ID itself.

# Implementation

Implement the smallest service/model extension required to manage download
tokens.

A download token must:

- be cryptographically random;
- be unpredictable;
- reference exactly one managed photo;
- support configured expiration;
- support explicit revocation;
- become invalid when its photo is deleted.

Use Python standard-library cryptographic random token generation.

Do not derive tokens from:

- photo IDs;
- filenames;
- timestamps;
- sequential values.

Persist token information using the existing local metadata/storage model.
Do not introduce a database.

# Download endpoint

Add a download endpoint conceptually equivalent to:

`GET /download/<token>`

The endpoint must:

- validate the token;
- resolve the corresponding photo through application services;
- reject unknown, malformed, expired or revoked tokens;
- reject tokens referring to deleted photos;
- return the original full-resolution image;
- use an appropriate download filename;
- never expose the internal filesystem path.

Do not use the photo ID itself as the download credential.

# QR code

Add QR code generation for a reviewed photo.

Use the `qrcode` package and reuse Pillow.

The encoded URL must have the form conceptually:

`<public_base_url>/download/<token>`

For example:

`http://192.168.1.42:5000/download/<token>`

The exact configured host must come from configuration.

Do not silently substitute `localhost` when `public_base_url` is missing.

If `public_base_url` is absent or invalid, expose a clear configuration error
instead of generating an unusable QR code.

# Review integration

Integrate the QR code into the existing review page.

The review page must:

- display the QR code for the reviewed photo;
- provide a short instruction indicating that it can be scanned to download
  the photo;
- preserve the existing Retake, Delete and Print actions.

Do not create a separate QR page unless the existing architecture requires it.

QR generation must not change the current review navigation behavior.

# Photo deletion and revocation

Deleting a photo must make every download token associated with that photo
invalid.

A previously generated URL must no longer provide access after deletion.

Do not rely solely on deleting the QR image itself for revocation.
Authorization must be enforced when handling the download request.

# Toolchain

Add `qrcode` as a runtime dependency using uv.

Execute the dependency change yourself.

Reuse Pillow already present in the project.

Do not add:

- a database;
- cloud storage;
- URL shortening;
- an authentication framework;
- external QR APIs.

# Documentation

Follow the repository-wide typing and documentation requirements.

In particular document:

- token ownership;
- token generation;
- token persistence;
- expiration semantics;
- revocation semantics;
- behavior after photo deletion;
- `public_base_url` requirements;
- trusted-LAN security assumptions.

# Tests

Add or update pytest tests covering at least:

- valid token;
- unknown token;
- malformed token;
- expired token;
- explicitly revoked token;
- token for a deleted photo;
- token mapping to the correct photo;
- QR URL construction;
- missing `public_base_url`;
- valid non-local `public_base_url`;
- download response for a valid photo;
- internal filesystem path not exposed.

Use deterministic test fixtures where time must be controlled.

Do not require network access or a physical phone in automated tests.

# Validation

Execute:

`uv run pyright`

and the relevant pytest tests.

Run the complete pytest suite because this milestone modifies gallery and
review behavior.

# Manual validation

Provide a manual LAN validation procedure using the OpenCV backend:

1. start the application so it is reachable from the LAN;
2. configure `public_base_url` with the actual LAN address;
3. capture a photo;
4. reach the review screen;
5. verify the QR code is displayed;
6. scan it from a second device connected to the same LAN;
7. download and open the full-resolution photo;
8. delete the photo;
9. verify that the previously scanned download URL no longer works.

# Expected result

Before editing:

- inspect the existing GalleryService, photo metadata, configuration and review
  implementation;
- briefly state where token ownership should live;
- list the files expected to change.

After implementation report only:

- files changed;
- token lifecycle implemented;
- route added;
- review integration added;
- dependency added;
- Pyright result;
- pytest result;
- manual LAN validation procedure.

Stop after this milestone.

Do not implement:

- slideshow;
- administration;
- CUPS;
- cloud sharing;
- final visual branding.