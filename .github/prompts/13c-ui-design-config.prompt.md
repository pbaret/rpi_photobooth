---
agent: agent
description: Create the configurable final visual design of the photobooth
---

# Goal

Create the near-final visual design of the existing photobooth frontend while
preserving all currently validated application behavior.

This is a genuine visual design and UI customization milestone.

The participant-facing interface must be designed primarily for a Lenovo
Phab 2 Pro used:

- in landscape orientation;
- in browser fullscreen/kiosk mode;
- as a dedicated touch interface.

Use a 2560 × 1440 landscape viewport as the primary design reference.

Do not hard-code the UI to this exact resolution.

The resulting design must also remain usable on similar landscape smartphone
and tablet viewports.

The administration interface does not share this constraint and may remain a
portrait-friendly, vertically scrollable interface.

# Existing functionality that must be preserved

The application is already functionally stable on PC.

The following features already exist and must not be reimplemented or
redesigned at the application-logic level:

- live camera preview;
- capture button;
- countdown;
- capture workflow;
- fullscreen white capture screen;
- `Ne bougez plus` capture message;
- browser-paint-before-capture behavior;
- review;
- retake;
- delete;
- print action;
- QR download;
- configurable Wi-Fi network name;
- Wi-Fi instruction above the QR code;
- slideshow;
- slideshow wake-up behavior;
- error states;
- administration;
- capability-driven camera settings.

In particular:

- do not reimplement `wifi_network_name`;
- do not change its configuration semantics;
- do not reimplement the white capture screen;
- do not change the capture timing mechanism unless a concrete visual defect
  requires a minimal correction.

Treat these as existing features whose presentation may be styled but whose
behavior must be preserved.

# Main objective

The same photobooth must be visually customizable for different events without
editing templates or CSS source code.

Examples include:

- wedding;
- birthday;
- company event;
- party;
- family event.

The configuration should be set through a dedicated config file. No need to make it editable at runtime.

The main configurable areas are:

1. visual theme : color palette, typography, button styles;
2. Background color or optional background image for the participant interface screens;
3. PREVIEW layout;
4. REVIEW layout.

Do not create a generic website builder.

# Sources

Before editing, inspect:

- all participant-facing templates;
- current booth CSS;
- current review CSS;
- slideshow and error-state CSS;
- existing frontend JavaScript;
- current administration UI;
- existing application configuration;
- the already implemented white capture screen;
- the already implemented Wi-Fi review instruction;
- `docs/architecture.md`;
- `docs/configuration.md`;
- applicable repository instructions.

Reuse the existing frontend and configuration architecture.

Do not create a parallel UI implementation.

# Phase 1: design proposal

Before modifying code, inspect the current UI and produce a concise design
proposal.

Describe:

- visual direction;
- default color palette;
- typography strategy;
- button hierarchy;
- spacing strategy;
- booth landscape composition;
- countdown treatment;
- capture treatment;
- review composition;
- QR treatment;
- slideshow treatment;
- error treatment;
- event-theme configuration model;
- configurable widget-positioning model.

Also identify:

- existing CSS that can be reused;
- CSS that should be simplified;
- templates that require changes;
- configuration models that require extension.

Do not propose changes to application workflows unless a concrete UI problem
requires them.

After presenting the proposal, continue with implementation without asking for
additional confirmation.

# Participant design principles

The participant UI should feel like a dedicated photographic appliance rather
than a normal website.

Prioritize:

1. the camera or photograph;
2. one obvious primary action;
3. large touch targets;
4. immediate readability;
5. visual simplicity;
6. high contrast;
7. consistent states;
8. effective use of the landscape viewport.

Avoid unnecessary:

- gradients;
- glassmorphism;
- excessive shadows;
- excessive animation;
- emojis;
- icon libraries;
- third-party fonts;
- dashboard-style components.

Subtle visual effects are acceptable when they contribute to a deliberate
design.

The objective is not minimal CSS.

The objective is a polished, coherent photobooth interface without unnecessary
decoration.

# Reference viewport

Design the participant experience primarily around:

2560 × 1440 landscape

Use responsive CSS rather than absolute pixel layouts tied to this resolution.

Prefer:

- CSS Grid;
- Flexbox;
- percentages;
- aspect-ratio;
- `min()`;
- `max()`;
- `clamp()`;
- CSS custom properties.

Normal participant workflow must not require scrolling.

Use the available landscape viewport intentionally.

# Portrait participant behavior

Portrait orientation is not a target participant layout.

Do not maintain a complete second participant design for portrait.

If the participant interface is opened in portrait orientation, it's their problem, and totally acceptable.

The admin interface is exempt from this constraint.

# Event theme model

Extend the existing typed configuration with a small explicit event-theme
model.

The configuration must provide useful customization without allowing arbitrary
CSS or HTML injection.

Do not store:

- arbitrary CSS declarations;
- arbitrary HTML;
- arbitrary JavaScript.

Theme values must be validated and converted into controlled CSS custom
properties or allowlisted CSS classes.

# Configurable colors

Support at least:

- participant background color;
- primary action color;
- primary action text color;
- foreground/text color;
- secondary/surface color where useful.

Color values must be validated.

Provide visually coherent defaults.

The photobooth must look complete without event-specific configuration.

# Background configuration

Participant screens must support either:

- a solid background color;
- or a local event background image.

If a background image is configured, support:

## Fit

At minimum:

- cover;
- contain.

## Position

Use allowlisted semantic positions such as:

- center;
- top;
- bottom;
- left;
- right;
- top-left;
- top-right;
- bottom-left;
- bottom-right.

Do not accept arbitrary CSS background-position expressions.

If no background image is configured, fall back cleanly to the configured
background color.

# Event background assets

Background images must remain local to the photobooth.

If an existing managed-asset mechanism exists, reuse it.

Otherwise implement the smallest safe mechanism necessary to select or upload
an event background image through the administration interface.

Store managed event images inside an application-controlled directory.

Use application-controlled filenames.

Validate uploaded content as an image using existing Pillow functionality.

Do not trust a client filename as a filesystem path.

Do not support arbitrary remote image URLs.

Do not introduce a general media-management system.

# Layout configuration philosophy

PREVIEW and REVIEW need configurable composition so that event artwork can
reserve different parts of the screen.

For example:

- an event background may contain artwork on the left and require the camera
  preview on the right;
- another event may require the photograph on the left and QR block on the
  right;
- another may require a centered composition.

The layout must therefore be configurable without modifying templates or CSS.

However, do not create a generic free-positioning engine.

# Widget positioning model

Use a constrained semantic positioning system rather than arbitrary X/Y pixel
coordinates.

Prefer reusable layout concepts such as:

- left;
- center;
- right;
- top-left;
- top-center;
- top-right;
- bottom-left;
- bottom-center;
- bottom-right.

Where widget size customization is useful, prefer a small controlled set such
as:

- small;
- medium;
- large;

or another similarly constrained typed representation.

The point is to represent layout intent rather than exact pixels.

CSS remains responsible for adapting that intent to the current viewport.

Do not implement:

- drag and drop;
- arbitrary `x` / `y` coordinates;
- arbitrary CSS grid expressions;
- arbitrary style strings.

# PREVIEW layout

Create a polished default layout for the booth IDLE state.

The camera preview must remain the dominant participant element.

The configurable PREVIEW composition should cover at least:

- camera preview position;
- camera preview relative size;
- capture button position;
- optional existing event/booth title position if currently displayed.

Provide a strong default layout requiring no configuration.

The preview must preserve its camera aspect ratio.

Where useful, allow a controlled display mode such as:

- contain;
- cover.

The capture button must always remain:

- visible;
- inside the usable viewport;
- comfortably touchable;
- distinguishable from event artwork.

Configuration must not allow an unusable layout.

# COUNTDOWN

Apply the selected event theme and PREVIEW composition to COUNTDOWN.

Keep the existing preview behavior.

Display the countdown prominently as an overlay.

Do not modify countdown timing or workflow semantics.

The countdown value must remain immediately readable over arbitrary event
backgrounds and camera content.

Use controlled contrast treatment if needed.

# CAPTURING

Preserve the existing CAPTURING implementation.

The existing behavior is intentionally:

- fullscreen white surface;
- black `Ne bougez plus` message;
- event background hidden;
- camera preview hidden;
- normal controls hidden;
- browser paints the white state before still capture is requested.

This state intentionally overrides event theming.

Only adjust its visual typography, spacing or responsive behavior if required
for consistency.

Do not modify its capture sequencing without a concrete defect.

# REVIEW layout

Create a polished landscape REVIEW experience.

The captured photograph should remain visually dominant.

The following major widgets already exist:

- captured photo;
- QR/download area;
- action buttons;
- Wi-Fi instruction.

Preserve their existing functionality.

Create a configurable REVIEW layout allowing the event configuration to select
the semantic placement of at least:

- captured photo;
- QR block;
- action block.

Provide a high-quality default landscape composition.

A two-column or asymmetric grid is appropriate for the default design.

For example, a typical default may dedicate the majority of the viewport to
the photograph and a smaller region to QR/download/actions.

Do not hard-code this example if another coherent composition fits the
existing frontend better.

# REVIEW actions

Preserve the existing actions:

- Reprendre;
- Imprimer;
- Supprimer.

Maintain a clear action hierarchy.

`Reprendre` should remain easy to discover.

`Imprimer` should remain clear.

`Supprimer` should be visibly destructive and secondary.

All controls must remain comfortably touchable.

# QR and Wi-Fi instruction

Preserve the already implemented Wi-Fi network-name configuration and message.

Do not change its configuration model unless required to integrate it with the
theme system.

Style the instruction as part of the QR/download visual block.

The QR code must remain:

- clearly visible;
- high contrast;
- sufficiently large to scan comfortably;
- visually separated from decorative background artwork.

Do not apply theme colors to the QR image itself if doing so could reduce
scanning reliability.

# SLIDESHOW

Apply the selected event theme to the existing slideshow.

Preserve existing slideshow logic and wake-up behavior.

Use the landscape viewport fully.

The displayed photo should remain dominant.

The wake-up instruction must remain clearly visible over different event
backgrounds and photos.

The first wake-up interaction must continue to return to the booth without
triggering capture.

# ERROR state

Create a visually coherent participant error state using the event theme where
appropriate.

Errors should communicate:

- that the operation failed;
- the available recovery action.

Do not expose technical diagnostics to participants.

Preserve existing error semantics.

# Shared participant components

Where useful, consolidate repeated visual concepts into reusable CSS classes or
Jinja partials.

Examples may include:

- participant action buttons;
- overlays;
- panels;
- status messages;
- QR block.

Do not introduce a component framework.

Do not refactor templates solely to create abstraction.

Create shared components only where existing duplication makes them useful.

# Administration

Do not redesign the administration interface as aggressively as the
participant interface.

Admin may:

- use portrait orientation;
- scroll vertically;
- remain relatively information dense.

Add an explicit event appearance section.

Expose the new configurable visual settings using appropriate native controls.

At minimum allow administration of:

- participant background color;
- participant background image;
- background fit;
- background position;
- primary action color;
- primary action text color;
- foreground/text color;
- secondary/surface color where implemented;
- PREVIEW layout options;
- REVIEW layout options.

The existing Wi-Fi network-name field remains where it currently logically
belongs.

Do not duplicate it.

# Admin layout controls

Use selects or similarly constrained controls for semantic positions and size
choices.

Do not expose raw CSS fields.

When practical, label options in a user-friendly manner.

For example, internal:

`top-right`

may be displayed to the administrator as:

`En haut à droite`

Do not couple persisted values to translated display labels.

# Live theme preview

Do not implement a full WYSIWYG editor.

If a simple preview of theme colors/background can be added using the existing
frontend without significant complexity, it is acceptable.

Do not let this optional preview expand the scope of the milestone.

The actual booth remains the source of truth for final visual validation.

# CSS architecture

Prefer a small set of validated CSS custom properties for theme values.

Conceptually:

- `--booth-background-color`;
- `--booth-primary-color`;
- `--booth-primary-text-color`;
- `--booth-foreground-color`;
- `--booth-surface-color`.

Use allowlisted classes for layout choices.

For example, conceptually:

- `layout-preview-left`;
- `layout-preview-center`;
- `layout-preview-right`.

The exact names should fit the existing frontend structure.

Do not construct raw stylesheets from configuration.

Keep visual behavior in CSS rather than scattering large inline-style
expressions through templates.

# Defaults and resilience

The default application theme must look intentional and complete.

Event customization is optional.

The UI must remain valid when:

- no background image exists;
- only some theme values are customized;
- the configured image has been removed or becomes unavailable;
- the Wi-Fi network name is empty;
- optional theme configuration is absent from older configuration files.

Use safe defaults.

Do not break existing configurations when introducing new theme fields.

# Frontend stack

Use only:

- existing Flask/Jinja2;
- HTML;
- CSS;
- vanilla JavaScript.

Do not add:

- React;
- Vue;
- Angular;
- Bootstrap;
- Tailwind;
- npm;
- JavaScript build tooling;
- CSS preprocessors;
- icon libraries;
- third-party fonts.

Do not introduce a frontend build step.

# Toolchain

Do not add runtime or development dependencies unless a concrete requirement
cannot be met using the existing stack.

Reuse Pillow for background-image validation if required.

Keep:

- uv;
- Pyright;
- pytest.

Do not add linting or formatting tools.

Do not change the build backend.

# Python quality

Follow repository-wide requirements for:

- complete type annotations;
- meaningful documentation;
- pytest tests.

Theme and layout configuration must use explicit typed models.

Do not use `dict[str, Any]` as the application-level theme model.

# Documentation

Document the parts whose behavior or design contract is not self-evident.

In particular document:

- event-theme ownership;
- theme defaults and overrides;
- validation of configured colors;
- management of background images;
- semantic widget positioning;
- mapping from configuration to CSS variables/classes.

Do not add documentation that merely explains obvious CSS declarations.

# Tests

Add or update pytest tests for server-side functionality introduced by this
milestone.

At minimum verify:

- default theme configuration;
- backward compatibility when theme fields are absent;
- valid color configuration;
- invalid color rejection;
- background image configuration;
- invalid/non-image upload rejection if upload is implemented;
- background fit validation;
- background position validation;
- valid PREVIEW layout values;
- invalid PREVIEW layout values;
- valid REVIEW layout values;
- invalid REVIEW layout values;
- theme settings persistence;
- admin theme update;
- generated participant views receive the expected validated theme/layout
  information;
- existing Wi-Fi network-name behavior remains unchanged;
- existing QR behavior remains unchanged;
- existing capture workflow remains unchanged.

Do not add a JavaScript test framework solely for this milestone.

# Regression protection

Pay particular attention to preserving functionality implemented before this
milestone.

Verify that UI changes do not change the semantics of:

- capture;
- countdown;
- white CAPTURING screen;
- paint-before-capture behavior;
- review;
- retake;
- delete;
- print;
- QR download;
- Wi-Fi instructions;
- slideshow;
- slideshow wake-up behavior;
- errors;
- administration authentication.

This is primarily a visual/configuration milestone.

Avoid modifying backend workflow code without a concrete requirement.

# Validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

# Manual design validation

Validate participant views at a landscape viewport matching the reference
device aspect and resolution:

2560 × 1440.

When available, also validate on the actual Lenovo Phab 2 Pro in landscape
fullscreen/kiosk mode.

Inspect every participant state:

- IDLE;
- COUNTDOWN;
- CAPTURING;
- REVIEW;
- SLIDESHOW;
- ERROR.

Normal participant workflow must not require scrolling.

# Event customization validation

Create at least three clearly different configurations using configuration
changes only.

## Theme A: default

Use:

- default background;
- default colors;
- default PREVIEW layout;
- default REVIEW layout.

It must look complete without customization.

## Theme B: artwork-oriented

Use:

- a local event background image;
- a PREVIEW layout positioned to leave part of the artwork visible;
- customized primary colors.

Do not modify template or CSS source code to achieve this layout.

## Theme C: alternate review

Use:

- different background/color configuration;
- a different REVIEW widget arrangement;
- the existing configured Wi-Fi network-name functionality.

Again, do not modify templates or CSS between themes.

The ability to produce these three visual variants using configuration alone
is an acceptance criterion of this milestone.

# Raspberry Pi independence

Do not encode assumptions about OpenCV timing into the UI.

The existing CAPTURING state must continue to support an unknown duration until
capture succeeds or fails.

Do not introduce Raspberry Pi-specific frontend code.

Do not implement speculative delays for future rpicam behavior.

The UI should later work unchanged with RpicamCameraBackend except for possible
hardware-driven timing refinements.

# Work method

Before editing:

1. inspect the complete existing participant UI;
2. summarize the current visual structure;
3. present the concise design proposal;
4. propose the typed event-theme configuration model;
5. propose the constrained PREVIEW layout model;
6. propose the constrained REVIEW layout model;
7. identify the files expected to change.

Then implement the milestone.

Do not ask for additional confirmation between the proposal and implementation.

Keep the implementation focused on the accepted design.

# Expected result

After implementation report only:

- files changed;
- final visual direction;
- event-theme configuration introduced;
- PREVIEW customization options;
- REVIEW customization options;
- background-image handling;
- administration changes;
- existing behaviors explicitly preserved;
- Pyright result;
- pytest result;
- manual landscape validation checklist;
- any visual behavior deliberately deferred until physical Raspberry Pi
  validation.

Stop after this milestone.

Do not implement:

- new capture behavior;
- new Wi-Fi functionality;
- hotspot provisioning;
- Wi-Fi password management;
- RpicamCameraBackend;
- Picamera2;
- CUPS;
- printer workflow changes.