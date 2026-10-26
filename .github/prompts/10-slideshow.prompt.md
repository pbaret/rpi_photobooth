---
agent: agent
description: Add inactivity slideshow and wake-up behavior
---

# Goal

Add slideshow mode to the existing booth page.

At the end of this milestone:

1. the booth starts in its normal IDLE state with live camera preview;
2. after the configured period without user activity, it enters SLIDESHOW;
3. existing gallery photos are displayed sequentially using thumbnails;
4. the slideshow displays "Touchez l'écran pour démarrer";
5. the first user interaction exits the slideshow;
6. the booth returns to IDLE with live preview;
7. the wake-up interaction must not trigger a capture.

Do not create a separate Flask page for slideshow mode.

# Context

The application already provides:

- the booth page and live preview;
- the capture workflow;
- GalleryService;
- thumbnails;
- the review workflow;
- local photo download.

SLIDESHOW is a transient booth state, like COUNTDOWN and CAPTURING.

The browser handles inactivity timing and slideshow presentation.

The server remains authoritative for application workflow state.

# Sources

Before editing, inspect only the relevant:

- booth template;
- booth JavaScript;
- booth workflow/state implementation;
- GalleryService;
- thumbnail/media routes;
- slideshow configuration;
- applicable repository instructions.

Extend the existing booth frontend instead of creating a second frontend
architecture.

# Inactivity behavior

Implement inactivity detection in a small dedicated vanilla JavaScript module
or in the existing booth state module if one already exists and remains
cohesive.

User activity includes at least:

- touch/pointer interaction;
- mouse interaction;
- keyboard interaction;
- successful navigation back to the booth.

Do not let the slideshow inactivity timer interfere with the capture countdown
timer.

COUNTDOWN and CAPTURING must never transition to SLIDESHOW because an
inactivity timer expired.

The inactivity timer is relevant only while the booth is eligible for
slideshow mode.

# Slideshow transition

When the configured inactivity timeout expires while the booth is IDLE:

1. enter SLIDESHOW;
2. hide or visually replace the normal booth controls;
3. display gallery thumbnails sequentially;
4. display the message:

   `Touchez l'écran pour démarrer`

Do not reload the entire page for each slideshow image.

Do not load all full-resolution photos into the browser.

Use existing generated thumbnails.

# Wake-up behavior

The first interaction while SLIDESHOW is active must:

1. exit SLIDESHOW;
2. stop slideshow rotation;
3. reset inactivity tracking;
4. restore IDLE;
5. restore the normal live preview and capture controls;
6. consume the wake-up interaction.

The same event must not trigger the "Prendre une photo" action.

This behavior is important for touchscreen kiosk use.

# Empty gallery

If no eligible photos exist when inactivity expires:

- still provide an inactive/waiting booth mode;
- display the wake-up instruction;
- do not show broken images;
- do not continuously poll or retry at high frequency.

The first interaction must still return to IDLE normally.

# Gallery refresh

Use GalleryService as the source of slideshow media.

Deleted photos must not appear.

Define a simple strategy for refreshing the available slideshow photos so that
new captures can eventually appear without reloading the application.

Keep this strategy lightweight.

Do not introduce:

- WebSockets;
- background workers;
- server push;
- frontend frameworks.

# Photo ordering

Use a simple deterministic ordering appropriate to the existing GalleryService.

Do not introduce randomization or sophisticated slideshow algorithms unless
they already exist in the accepted architecture.

# Functional UI

SLIDESHOW is part of the existing booth page.

Use only:

- existing Flask/Jinja infrastructure;
- HTML;
- CSS;
- vanilla JavaScript.

The slideshow must:

- use the available viewport;
- preserve photo aspect ratio;
- work in portrait and landscape;
- avoid normal page scrolling;
- make the wake-up instruction clearly visible;
- transition back to the booth without requiring browser navigation controls.

This is functional UX, not final visual branding.

# Toolchain

Do not add:

- frontend dependencies;
- JavaScript packages;
- scheduling libraries;
- WebSockets;
- background workers.

Use browser timers and the existing Flask/gallery infrastructure.

# Documentation

Follow repository-wide documentation requirements.

Document the non-obvious frontend behavior, especially:

- what constitutes activity;
- when inactivity tracking is active;
- separation from capture countdown;
- slideshow lifecycle;
- wake-up event consumption;
- empty-gallery behavior;
- thumbnail refresh strategy.

Do not add comments that merely restate JavaScript statements.

# Tests

Add or update pytest tests for server-side slideshow behavior, including:

- gallery with eligible photos;
- empty gallery;
- deleted photos excluded;
- thumbnail URLs rather than full-resolution images;
- configured slideshow disabled if relevant to the existing configuration.

Do not attempt to reproduce a browser timer using Python tests.

Keep browser state logic small and explicit enough to validate manually.

# Validation

Execute:

`uv run pyright`

and the relevant pytest tests.

Run the complete pytest suite because slideshow behavior interacts with the
booth workflow and gallery.

# Manual validation

Provide a manual OpenCV validation procedure using a short inactivity timeout,
for example 10 seconds:

1. open the booth and verify live preview;
2. do not interact for the configured timeout;
3. verify transition to slideshow;
4. verify thumbnails rotate;
5. verify the wake-up instruction is visible;
6. touch/click once;
7. verify immediate return to IDLE and live preview;
8. verify that this interaction does not start a capture;
9. leave the booth inactive again and verify slideshow can enter a second time;
10. repeat with an empty gallery.

# Expected result

Before editing:

1. inspect the existing booth state handling and frontend code;
2. identify where inactivity state should live;
3. explain briefly how countdown and inactivity timers will remain independent;
4. list files expected to change.

After implementation report only:

- files changed;
- activity events handled;
- slideshow lifecycle implemented;
- gallery refresh strategy;
- Pyright result;
- pytest result;
- manual validation procedure.

Stop after this milestone.

Do not implement:

- administration;
- CUPS;
- final visual branding.