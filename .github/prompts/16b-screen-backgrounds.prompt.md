---
agent: agent
description: Support independent backgrounds for Preview, Review and Slideshow
---

# Goal

Extend the existing configurable event-theme system so the three main
participant-facing interfaces can use independent backgrounds:

- PREVIEW;
- REVIEW;
- SLIDESHOW.

The purpose is to let event artwork be designed specifically around the layout
and widgets of each screen.

At the end of this milestone, an administrator must be able to configure a
different background for each of these three screens without modifying HTML,
CSS or application code.

# Context

The application already provides:

- a typed configurable event-theme system;
- configurable participant background color/image;
- managed local background images;
- background fit and position;
- configurable PREVIEW layout;
- configurable REVIEW layout;
- Admin appearance configuration;
- slideshow;
- fully implemented participant workflows.

Reuse the existing theme and managed-asset architecture.

Do not create a second theme system.

This milestone changes background configuration only.

Preserve the existing:

- colors;
- button styling;
- layout configuration;
- capture workflow;
- REVIEW workflow;
- slideshow behavior;
- white CAPTURING screen.

# Background model

Replace or extend the current single participant background configuration with
three explicit screen-background configurations:

- preview background;
- review background;
- slideshow background.

Each screen background must support the same existing background features:

- background color;
- optional local background image;
- image fit;
- image position.

Reuse the existing typed background model rather than duplicating four fields
three times if the current architecture allows it cleanly.

Conceptually prefer:

EventTheme
  -> preview_background: ScreenBackground
  -> review_background: ScreenBackground
  -> slideshow_background: ScreenBackground

rather than unrelated flat fields.

Keep the implementation simple and fully typed.

# PREVIEW

Use `preview_background` for the normal booth participant interface.

It must apply to:

- IDLE;
- COUNTDOWN where the existing design displays the booth background.

Preserve the existing configurable PREVIEW widget layout.

Do not change preview or capture behavior.

# CAPTURING

Do not apply any configurable event background during CAPTURING.

Preserve the existing behavior:

- fullscreen white surface;
- black `Ne bougez plus` message;
- camera preview hidden;
- event background hidden.

The existing white capture screen intentionally overrides all event
background configuration.

# REVIEW

Use `review_background` for the dedicated REVIEW interface.

Preserve:

- captured photo;
- QR block;
- Wi-Fi instruction;
- Retake;
- Print;
- Delete;
- existing configurable REVIEW widget layout.

The purpose of the independent background is to allow artwork specifically
designed around these REVIEW widgets.

Do not change REVIEW behavior.

# SLIDESHOW

Use `slideshow_background` for SLIDESHOW.

Preserve:

- existing slideshow photo display;
- thumbnail/media behavior;
- wake-up message;
- wake-up interaction consumption;
- return to IDLE.

The slideshow background must not replace the displayed slideshow photo.

It is the background/surface around or behind the existing slideshow content.

# Admin configuration

Update the existing appearance/theme section of Admin.

Create three clearly separated background configuration groups:

## Écran Preview

Configure:

- background color;
- background image;
- fit;
- position.

## Écran Review

Configure:

- background color;
- background image;
- fit;
- position.

## Écran Slideshow

Configure:

- background color;
- background image;
- fit;
- position.

Reuse existing upload/select controls and validation behavior.

Do not duplicate managed background-image code.

Do not add independent theme colors, button colors or typography settings for
each screen.

Only the backgrounds become screen-specific.

The rest of the event visual theme remains shared.

# Managed background images

Continue using the existing managed local asset mechanism.

The three screen backgrounds may:

- use three different images;
- reuse the same image;
- use only colors;
- combine image and fallback color independently.

Removing or replacing one screen background must not accidentally remove an
image still used by another screen.

Review the existing asset deletion/replacement logic carefully for this case.

Do not create duplicate image files merely because the same managed image is
used by multiple screens.

# Backward compatibility

Existing event configurations currently contain a single participant
background.

They must continue to load successfully.

Implement a clear backward-compatible migration/default strategy.

For an older configuration containing one participant background, use that
existing background as the default for:

- PREVIEW;
- REVIEW;
- SLIDESHOW;

unless the current configuration architecture provides a cleaner equivalent.

Do not require users to manually recreate their existing event theme.

Once persisted using the new model, the configuration may store the three
independent screen backgrounds explicitly.

Document this behavior.

# CSS integration

Reuse the existing theme-to-CSS architecture.

Do not introduce:

- arbitrary inline CSS from configuration;
- arbitrary CSS selectors;
- raw style configuration.

Continue using validated CSS custom properties and/or allowlisted classes.

Apply the correct screen background based on the participant interface being
rendered.

Avoid copying large CSS blocks three times.

Keep common background rendering behavior reusable.

# Layout independence

Background selection and widget layout remain separate concepts.

For example:

PREVIEW
  background = wedding-preview.jpg
  layout = preview-right

REVIEW
  background = wedding-review.jpg
  layout = photo-left / qr-right

SLIDESHOW
  background = wedding-slideshow.jpg

Do not encode widget coordinates into background configuration.

Do not modify the existing constrained layout model.

This separation is intentional so event artwork and UI composition can evolve
independently.

# Toolchain

Do not add dependencies.

Reuse:

- existing typed configuration;
- existing managed event assets;
- existing Flask/Jinja frontend;
- existing CSS;
- existing admin implementation;
- Pillow where already used for image validation.

Do not add:

- frontend framework;
- asset-management library;
- database;
- JavaScript framework;
- CSS framework.

Do not change the build backend.

# Documentation

Follow repository-wide typing and documentation requirements.

Document:

- screen-specific background ownership;
- relationship with the shared event theme;
- fallback colors;
- asset reuse;
- backward compatibility;
- old-configuration migration behavior;
- why CAPTURING does not use a configurable background.

Update `docs/configuration.md` where appropriate.

# Tests

Add or update pytest tests covering at least:

## Configuration

- three default screen backgrounds;
- independent PREVIEW background;
- independent REVIEW background;
- independent SLIDESHOW background;
- different colors for each screen;
- different images for each screen;
- same image reused by several screens;
- invalid background values rejected.

## Backward compatibility

- old configuration with one participant background still loads;
- old background is applied to all three screens according to the selected
  migration strategy;
- saving migrated configuration succeeds;
- existing theme settings remain unchanged.

## Assets

- replacing PREVIEW background does not affect REVIEW;
- replacing REVIEW background does not affect SLIDESHOW;
- shared image remains available while another screen still references it;
- invalid/non-image assets remain rejected through the existing validation.

## Rendering

- PREVIEW receives preview background;
- REVIEW receives review background;
- SLIDESHOW receives slideshow background;
- COUNTDOWN preserves expected PREVIEW styling;
- CAPTURING remains white and ignores event backgrounds;
- existing Wi-Fi/QR behavior remains unchanged;
- existing layout configuration remains unchanged.

## Admin

- all three background groups are displayed;
- independent settings persist;
- existing shared theme settings remain shared;
- no arbitrary CSS values are accepted.

# Validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

# Manual validation

Configure three visually obvious backgrounds, for example:

- PREVIEW: red background;
- REVIEW: blue background;
- SLIDESHOW: green background.

Verify:

1. IDLE displays the PREVIEW background;
2. COUNTDOWN retains the expected PREVIEW presentation;
3. CAPTURING still becomes completely white;
4. REVIEW displays the REVIEW background;
5. return to the booth restores the PREVIEW background;
6. inactivity enters SLIDESHOW with the SLIDESHOW background;
7. wake-up returns to PREVIEW with its background;
8. existing participant workflows remain unchanged.

Then repeat using three different local event background images.

Verify that each image can be designed around its corresponding screen layout.

# Expected result

Before editing:

1. inspect the existing EventTheme/background model;
2. inspect existing managed-asset ownership and deletion behavior;
3. inspect PREVIEW, REVIEW and SLIDESHOW styling;
4. describe the smallest model change required;
5. describe the backward-compatibility strategy;
6. list files expected to change.

Then implement the milestone.

After implementation report only:

## Configuration

Describe the final screen-background model.

## Backward compatibility

Describe how existing single-background configurations are handled.

## Admin

List the three background configuration sections.

## Files changed

List changed files.

## Automated validation

Report actual:

- Pyright result;
- pytest result;
- platform.

## Manual validation

Report PASS, FAIL or SKIP for:

- PREVIEW independent background;
- REVIEW independent background;
- SLIDESHOW independent background;
- white CAPTURING screen preserved;
- background image reuse;
- existing layout behavior preserved.

Stop after this milestone.

Do not implement:

- per-screen typography;
- per-screen button themes;
- arbitrary CSS;
- arbitrary widget coordinates;
- new participant workflows;
- unrelated UI redesign.