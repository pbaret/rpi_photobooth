# Functional user interface

This milestone must make the capture workflow usable from the booth page.

Extend the existing booth page created by the preview milestone.

The booth page must visually represent:

- IDLE;
- COUNTDOWN;
- CAPTURING;
- ERROR.

Do not create separate Flask pages for these transient states.

## IDLE

When IDLE:

- display the live camera preview;
- make the preview visually dominant;
- display a large touch-friendly "Prendre une photo" button;
- make the booth usable without normal desktop browser controls.

## COUNTDOWN

When capture starts:

- disable additional capture actions;
- keep the preview visible;
- display the current countdown value prominently over the preview;
- update the displayed value during the countdown.

The browser may handle the visual countdown timing, but the server remains
authoritative over the capture workflow and must reject concurrent capture
requests.

## CAPTURING

After the countdown:

- display an explicit capture-in-progress state;
- keep capture actions disabled;
- do not allow another capture operation to start.

## ERROR

On a recoverable capture error:

- display a clear user-facing error state;
- provide a way to return to IDLE;
- do not expose internal exception details.

## Layout

The booth page must:

- use the available browser viewport;
- prioritize the camera preview;
- preserve preview aspect ratio;
- work in portrait and landscape;
- avoid normal page scrolling;
- provide touch targets of at least 48 CSS pixels.

Use only:

- existing Flask/Jinja infrastructure;
- HTML;
- CSS;
- vanilla JavaScript.

Do not add frontend dependencies.

This is functional UX, not final visual design.

Do not spend effort on:

- final branding;
- sophisticated animations;
- custom fonts;
- visual effects;
- UI functionality belonging to future milestones.