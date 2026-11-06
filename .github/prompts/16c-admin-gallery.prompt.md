---
agent: agent
description: Add an admin-only gallery for managing captured photos
---

# Goal

Add a dedicated photo-management gallery accessible only from the authenticated
administration interface.

At the end of this milestone, an administrator must be able to:

1. open the existing administration interface;
2. navigate to a dedicated Gallery page;
3. browse previously captured photos using existing thumbnails;
4. delete a photo;
5. reprint a photo using the configured PrinterBackend.

This page is intended to manage potentially many photos.

Do not reuse the participant REVIEW page as the gallery.

Do not create a second gallery/storage implementation.

# Context

The application already provides:

- authenticated administration;
- GalleryService;
- opaque photo identifiers;
- persistent photo metadata;
- generated thumbnails;
- photo deletion;
- participant REVIEW;
- PrinterBackend;
- NullPrinterBackend;
- CupsPrinterBackend;
- printing configuration;
- duplicate-print protection.

Reuse these existing services and domain models.

The new page is an administration view over the existing gallery.

# Sources

Before editing, inspect only the relevant:

- GalleryService;
- photo metadata model;
- thumbnail management;
- existing photo deletion service/route;
- PrinterBackend;
- CupsPrinterBackend;
- existing print workflow;
- admin authentication;
- admin routes and templates;
- existing administration navigation;
- applicable repository instructions.

Do not duplicate business logic already implemented elsewhere.

# Admin navigation

Add a clearly identifiable Gallery entry to the existing administration
interface.

Conceptually:

Admin
  -> Gallery

Use a dedicated route such as:

`GET /admin/gallery`

The route must use the same authentication/protection mechanism as the rest of
the administration interface.

An unauthenticated user must not be able to:

- open the gallery;
- retrieve gallery-management data;
- invoke delete actions;
- invoke reprint actions.

Do not expose the admin gallery through participant navigation.

# Gallery display

Display managed photos as a responsive thumbnail gallery.

Use the thumbnails already generated and managed by GalleryService.

Do not:

- load full-resolution original JPEG files simply to display the gallery;
- generate a second set of thumbnails;
- regenerate thumbnails on every page request.

Each gallery item must show at minimum:

- the existing thumbnail;
- a Delete action;
- a Print action.

Where existing metadata makes it useful without clutter, a small capture
timestamp may also be displayed.

Do not display:

- filesystem paths;
- download tokens;
- internal metadata;
- technical camera information.

# Large-gallery behavior

Design the page for potentially many captured photos.

Do not render an unlimited number of gallery items in one response.

Implement simple pagination.

Prefer a straightforward page-number model rather than infinite scrolling.

Use a sensible default page size, for example around 24 thumbnails, unless the
existing gallery architecture suggests a better value.

The page must provide navigation to:

- previous page;
- next page;

and may provide explicit page numbers if this remains simple.

Ordering should be deterministic.

Use newest photos first unless the existing GalleryService already defines a
different intentional ordering.

Pagination must operate on gallery metadata and thumbnails.

Do not load every original JPEG in order to paginate.

# Empty gallery

If no photos exist, display a clear empty state.

For example:

`Aucune photo dans la galerie.`

Do not display broken thumbnail placeholders.

# Delete action

Each gallery item must provide:

`Supprimer`

Deletion must:

1. require explicit confirmation in the browser;
2. use POST;
3. identify the photo only by its opaque photo ID;
4. resolve the photo through GalleryService;
5. reuse the existing photo-deletion behavior;
6. delete/invalidate the original photo according to existing semantics;
7. remove/invalidate its thumbnail;
8. invalidate associated QR/download access according to existing behavior;
9. return the administrator to an appropriate gallery page.

Do not reimplement filesystem deletion inside the admin route.

Do not accept a filesystem path from the browser.

# Delete confirmation

Use a simple confirmation appropriate to the existing frontend.

The administrator should understand that deletion removes the stored photo.

Do not create a complex modal framework solely for this operation.

Use existing HTML/CSS/vanilla JavaScript patterns.

# Pagination after deletion

Handle deletion of the last item on a page gracefully.

For example, if deleting the only remaining item on page 4 means that page 4
no longer exists, redirect to the nearest valid gallery page instead of
displaying an invalid or empty pagination state.

# Print action

Each gallery item must provide:

`Imprimer`

This action means:

reprint the existing full-resolution photo.

The thumbnail must never be sent to the printer.

Printing must:

1. use POST;
2. identify the photo through its opaque photo ID;
3. resolve the original managed JPEG through GalleryService;
4. use the existing PrinterBackend;
5. use the currently configured printing settings;
6. use CupsPrinterBackend when CUPS printing is active;
7. preserve NullPrinterBackend behavior in development;
8. return a clear success or failure status to the administrator.

Do not create a new printing implementation.

Do not invoke `lp` directly from the admin route.

# Reprint semantics

An administrator intentionally pressing `Imprimer` from the gallery is a new
print request.

It must therefore be possible to print the same stored photo more than once
through separate explicit button presses.

However, protect a single button press against accidental duplicate
submission caused by:

- double tap;
- browser retry;
- repeated POST delivery.

Reuse or extend the existing print idempotency mechanism.

Do not permanently prevent intentional reprints of the same photo.

# Print feedback

After submission, keep the administrator in the gallery.

Display a concise status such as:

`Photo envoyée à l'imprimante.`

Where already supported by the printing domain, the protected admin UI may
also display the CUPS job identifier.

On failure, display a useful administrative error without exposing unbounded
raw subprocess output.

Do not claim that the physical print completed merely because CUPS accepted
the job.

# Gallery UI

The gallery belongs to the administration experience, not the participant
experience.

It does not need to follow the participant landscape-only layout.

It may:

- scroll vertically;
- work in portrait;
- work in landscape;
- display multiple thumbnail cards per row.

Use a responsive CSS grid.

Each item should have a simple structure conceptually equivalent to:

+----------------------+
|                      |
|      THUMBNAIL       |
|                      |
+----------------------+
|    capture date      |
|                      |
| Imprimer  Supprimer  |
+----------------------+

Adapt the exact presentation to the existing administration design.

Do not introduce a frontend framework.

# Thumbnail behavior

Preserve thumbnail aspect ratio.

Do not stretch images.

Use CSS to constrain thumbnails to a consistent gallery-card area.

Do not serve original images through the thumbnail element merely for visual
quality.

If a metadata entry exists but its thumbnail is unexpectedly missing, handle
the condition gracefully.

Do not crash the complete gallery because of one invalid item.

Use the existing gallery consistency behavior where possible.

# Admin authorization

All gallery routes and mutations must use the existing admin authentication
mechanism.

Do not create a separate password or authentication scheme.

Protect at minimum:

- gallery listing;
- delete;
- print.

Do not assume that hiding links in HTML provides authorization.

Authorization must be enforced server-side.

# Routes

Prefer a small dedicated admin-gallery route set consistent with the existing
Flask architecture.

Conceptually:

`GET /admin/gallery`

`POST /admin/gallery/<photo_id>/delete`

`POST /admin/gallery/<photo_id>/print`

Exact route names should follow existing project conventions.

Routes must remain HTTP adapters.

They must delegate:

- gallery operations to GalleryService;
- printing to the existing printing service/backend.

Do not place storage or CUPS implementation logic in Flask routes.

# Toolchain

Do not add dependencies.

Reuse:

- Flask;
- Jinja2;
- existing CSS;
- vanilla JavaScript;
- GalleryService;
- PrinterBackend;
- existing thumbnails.

Do not add:

- database;
- JavaScript framework;
- pagination package;
- image-gallery package;
- CUPS dependency;
- frontend build tooling;
- linting or formatting tools.

Do not change the build backend.

# Configuration

Do not introduce new configuration unless required by a concrete implementation
need.

If gallery page size is configurable, keep it simple and typed.

A fixed application default around 24 thumbnails per page is acceptable and
preferred unless configurability provides a concrete benefit.

Do not add unnecessary admin settings.

# Documentation

Follow repository-wide typing and documentation requirements.

Document:

- admin-gallery responsibility;
- authorization boundary;
- pagination behavior;
- thumbnail-only listing behavior;
- deletion delegation;
- print/reprint semantics;
- duplicate-print protection;
- missing/corrupt gallery-item behavior.

Do not duplicate GalleryService documentation in the route code.

# Tests

Add or update pytest tests covering at least:

## Authorization

- unauthenticated gallery access rejected;
- unauthenticated delete rejected;
- unauthenticated print rejected;
- authenticated gallery access succeeds.

## Listing

- empty gallery;
- one photo;
- multiple photos;
- newest-first ordering;
- thumbnails used rather than original images;
- missing thumbnail handled safely;
- unknown or malformed metadata handled according to existing gallery
  semantics.

## Pagination

- first page;
- next page;
- previous page;
- page containing the final item;
- invalid page number;
- page beyond the available range;
- deletion of the only item on the final page.

## Delete

- successful delete;
- unknown photo ID;
- already deleted photo;
- thumbnail removed/invalidated;
- original no longer accessible;
- associated download access remains revoked according to existing behavior;
- path traversal attempt rejected.

## Print

- successful print submission;
- original JPEG used rather than thumbnail;
- currently configured print settings reused;
- NullPrinterBackend behavior;
- CupsPrinterBackend behavior through a fake process boundary;
- unknown photo ID;
- deleted photo cannot be printed;
- accidental duplicate submission produces one print job;
- later explicit reprint of the same photo is allowed;
- print failure keeps the gallery usable.

## Regression

Verify that existing:

- participant REVIEW delete;
- participant REVIEW print;
- QR download;
- slideshow;
- normal GalleryService behavior

remain functional.

# Validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

# Manual validation

Validate using a populated gallery containing enough photos to exercise the
layout and pagination.

At minimum:

1. authenticate to Admin;
2. open Gallery;
3. verify only thumbnails are displayed;
4. verify several rows render correctly;
5. navigate between gallery pages;
6. print one existing photo;
7. verify the full-resolution original is printed;
8. print the same photo again through a second explicit action;
9. verify both intentional print jobs are accepted;
10. delete another photo;
11. verify it disappears from the gallery;
12. verify its original file is no longer available through the application;
13. verify its previous QR/download access no longer works;
14. refresh the gallery;
15. verify deletion remains persistent;
16. verify admin navigation back to the main Admin page.

On the Raspberry Pi with CupsPrinterBackend active, physically validate at
least one reprint through the new Gallery page.

# Expected result

Before editing:

1. inspect GalleryService and existing pagination/listing capabilities;
2. inspect existing admin authentication;
3. inspect REVIEW delete behavior;
4. inspect existing printing/idempotency behavior;
5. explain which existing services will be reused;
6. describe the pagination approach;
7. list files expected to change.

Then implement the milestone.

After implementation report only:

## Files changed

List changed files.

## Gallery behavior

Summarize:

- route;
- ordering;
- page size;
- pagination;
- thumbnail usage.

## Actions

Summarize:

- deletion behavior;
- reprint behavior;
- duplicate protection.

## Reuse

Explicitly identify which existing GalleryService and PrinterBackend behavior
was reused rather than duplicated.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform.

## Manual validation

Report PASS, FAIL or SKIP for:

- gallery access;
- thumbnail display;
- pagination;
- deletion;
- intentional reprint;
- duplicate prevention;
- real CP1000 reprint where tested.

Stop after this milestone.

Do not implement:

- gallery search;
- gallery filtering;
- bulk deletion;
- bulk printing;
- photo editing;
- photo download from admin;
- new thumbnail sizes;
- participant-facing gallery;
- new printer functionality;
- unrelated UI redesign.