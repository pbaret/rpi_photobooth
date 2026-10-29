---
agent: agent
description: Polish the photobooth UI for smartphone landscape kiosk use
---

# Goal

Consolidate the existing photobooth frontend into a coherent touch-first
smartphone landscape experience without changing the existing application
workflows.

The current user experience and navigation are functionally correct.

Preserve the existing workflow and interactions.

This milestone focuses on:

1. optimizing the participant-facing booth for smartphone landscape use;
2. improving visual consistency across booth states;
3. adding a white capture screen that acts as supplemental light;
4. adding the booth Wi-Fi network name above the review QR code.

Do not redesign workflows that already work.

Do not add new product functionality beyond the two explicitly requested
changes.

# Context

The PC implementation is complete and stable.

The existing application already provides:

- camera preview;
- capture button;
- countdown;
- capture workflow;
- review;
- retake;
- delete;
- print placeholder;
- QR download;
- slideshow;
- administration;
- camera settings.

The participant-facing booth is intended to run primarily on a smartphone
used in landscape orientation.

Portrait layout is not a design target for the participant workflow.

The administration interface may remain portrait-friendly and scrollable.

The existing frontend uses:

- Flask;
- Jinja2;
- HTML;
- CSS;
- vanilla JavaScript.

Keep this toolchain.

# Sources

Before editing, inspect only the relevant:

- booth template;
- review template;
- slideshow UI;
- error-state UI;
- administration template where required for the new configuration value;
- existing CSS;
- existing booth JavaScript;
- capture workflow;
- configuration model;
- QR/review implementation;
- applicable repository instructions.

Preserve existing routes, state transitions and behavior unless a change is
explicitly required below.

# Participant UI target

Optimize these participant-facing states for a smartphone in landscape
orientation:

- IDLE;
- COUNTDOWN;
- CAPTURING;
- REVIEW;
- ERROR;
- SLIDESHOW.

Assume the target device is used in kiosk-like landscape mode.

Prioritize:

- use of the available viewport;
- camera/photo content;
- large touch targets;
- strong visual hierarchy;
- minimal text;
- immediate understanding of the primary action.

Normal participant workflow should not require scrolling.

Do not spend effort optimizing the participant workflow for smartphone
portrait orientation.

It should remain reasonably safe if opened in another viewport, but landscape
is the explicit design target.

# Preserve the existing UX

Do not change existing navigation or action semantics merely for visual
reasons.

In particular preserve the existing behavior of:

- capture;
- countdown;
- review;
- retake;
- delete;
- print;
- QR download;
- slideshow wake-up;
- administration access.

At any participant-facing state, maintain a clear primary action where one
exists.

Do not introduce additional confirmation steps except for already destructive
actions such as deletion.

# IDLE

The camera preview should be visually dominant.

Optimize the layout for landscape smartphone dimensions.

The capture action must:

- remain immediately identifiable;
- remain comfortably touchable;
- not obscure an unnecessarily large portion of the preview.

Avoid desktop-style page layout around the camera preview.

The booth should feel like a fullscreen appliance rather than a normal web
page.

# COUNTDOWN

Keep the live preview visible during countdown.

Display the countdown value prominently enough to be immediately readable.

Do not change the existing countdown timing or server-side workflow.

The countdown should visually prepare the user for the transition to the
capture screen.

# CAPTURING: white supplemental-light screen

Change the visual behavior after the countdown and before REVIEW.

When countdown completes, replace the booth display with a fullscreen white
capture surface.

The capture surface must:

- cover the complete participant viewport;
- use pure or near-pure white;
- not display the camera preview;
- not display navigation controls;
- display the following message prominently in black:

  `Ne bougez plus`

The purpose of this screen is to maximize the smartphone display brightness
visible to the subject and provide supplemental frontal light during the
actual photograph.

The message must remain clearly readable while keeping most of the screen
white.

# Capture timing

The white capture surface must be rendered by the browser before the actual
still capture is triggered.

Do not simply:

1. change a CSS class;
2. synchronously trigger capture immediately afterwards;

if that can cause the browser to perform the capture request before painting
the white screen.

Use a small and explicit browser-side transition that allows the white state
to be painted before requesting the still capture.

Keep this mechanism simple.

Do not add arbitrary long delays solely for visual effect.

Do not alter the existing server authority over capture state.

The expected sequence is:

IDLE
  -> COUNTDOWN
  -> white CAPTURING screen visible
  -> still capture requested/performed
  -> REVIEW

If capture fails, leave the white capture state and show the existing
recoverable ERROR behavior.

# Display brightness limitation

Do not attempt to control device brightness using unsupported or
permission-sensitive browser APIs.

The application only displays a white fullscreen surface.

Actual smartphone display brightness remains controlled by the device/user.

Do not represent this feature as a real synchronized photographic flash.

# REVIEW

Keep the existing review functionality:

- photo display;
- retake;
- delete;
- print;
- QR download.

Optimize the layout for smartphone landscape use.

The captured photo should remain visually dominant.

Actions should remain large and clearly distinguishable.

Deletion should remain visually secondary to normal positive actions.

# QR Wi-Fi instruction

Add a configurable booth Wi-Fi network name to the application configuration.

Use a clear configuration field named conceptually:

`wifi_network_name`

Use the existing typed configuration and persistence architecture.

Do not create a separate configuration mechanism.

The Wi-Fi network name is display information only.

Do not store or request a Wi-Fi password as part of this milestone.

# QR review message

Above the existing QR code, display an instruction that tells the user to
connect to the booth Wi-Fi network before scanning the QR code.

Use the configured Wi-Fi network name.

The French user-facing message should be conceptually equivalent to:

`Connectez-vous au réseau Wi-Fi « <wifi_network_name> » puis scannez le QR code pour télécharger votre photo.`

Keep the message concise and clearly associated with the QR code.

The configured network name must be safely rendered as text.

Do not interpret it as HTML.

If no Wi-Fi network name is configured:

- do not display an empty or broken sentence;
- show a generic instruction appropriate to the existing QR workflow.

For example:

`Connectez-vous au réseau Wi-Fi du photobooth puis scannez le QR code pour télécharger votre photo.`

# Configuration integration

Add `wifi_network_name` to the existing typed configuration model.

The value must:

- have a sensible empty/default state;
- be persisted through the existing configuration mechanism;
- be editable from the existing administration interface;
- be available to the review view.

Do not treat the Wi-Fi network name as a secret.

Do not add Wi-Fi provisioning or operating-system network configuration.

This application displays the network name only.

It does not configure the Raspberry Pi Wi-Fi access point in this milestone.

# SLIDESHOW

Preserve existing slideshow behavior.

Optimize it for landscape participant use.

Keep:

- gallery thumbnails/photos visually dominant;
- wake-up instruction clearly visible;
- existing wake-up event consumption behavior.

The first wake-up interaction must still return to IDLE without triggering
capture.

# ERROR states

Keep error states simple and recoverable.

A participant should understand:

- that the booth could not complete the operation;
- what action returns to a usable state.

Do not display:

- stack traces;
- filesystem paths;
- subprocess errors;
- technical diagnostics.

# Administration UI

Do not redesign the administration interface extensively.

The administration interface may:

- use portrait orientation;
- scroll vertically;
- remain information-dense.

Only make visual changes required for consistency or to add the new
`wifi_network_name` configuration field.

Do not spend this milestone creating a polished administration dashboard.

# Visual design principles

Improve visual consistency without inventing unnecessary decoration.

Prefer:

- clear hierarchy;
- large photography area;
- generous touch targets;
- simple typography;
- consistent buttons;
- consistent spacing;
- clear active/loading/disabled states;
- high contrast;
- restrained color usage.

Avoid gratuitous:

- gradients;
- glassmorphism;
- decorative shadows;
- excessive animation;
- emojis;
- third-party fonts;
- icon libraries.

Do not make the application look like a generic SaaS dashboard.

It should feel like a simple dedicated photobooth appliance.

# Frontend architecture

Reuse the existing frontend structure.

Do not introduce:

- React;
- Vue;
- Angular;
- Bootstrap;
- Tailwind;
- npm;
- a JavaScript build system;
- a CSS preprocessor;
- third-party UI dependencies.

Use:

- Jinja2;
- HTML;
- CSS;
- vanilla JavaScript.

Do not reorganize frontend files unless the existing structure makes this
milestone materially harder to implement.

# Toolchain

Do not add runtime or development dependencies.

Do not add linting or formatting tools.

Keep:

- uv;
- Pyright;
- pytest;
- existing Python/frontend dependencies.

# Python quality

Follow the existing repository requirements for:

- complete type annotations;
- complete component documentation;
- pytest tests.

The new `wifi_network_name` configuration must use the existing typed
configuration model.

Do not weaken existing Pyright settings.

# Frontend documentation

Document only non-obvious frontend behavior.

In particular, document:

- why the CAPTURING screen is white;
- how the browser is allowed to paint it before still capture starts;
- why wake-up interactions are consumed during slideshow.

Do not add comments that merely restate CSS or JavaScript statements.

# Tests

Add or update pytest tests for the Python/server-side behavior introduced by
this milestone.

At minimum verify:

- default `wifi_network_name`;
- configured Wi-Fi network name persistence;
- admin update of `wifi_network_name`;
- configured Wi-Fi network name appears safely in the review response;
- missing Wi-Fi network name produces the generic QR instruction;
- existing QR download behavior remains unchanged;
- existing workflow routes remain functional.

Do not introduce a JavaScript test framework solely for this milestone.

Do not attempt to test browser painting or physical display brightness through
pytest.

# Validation

Execute:

`uv run pyright`

and:

`uv run pytest`

Both must pass.

# Manual validation

Provide a manual validation checklist for a smartphone in landscape mode.

At minimum validate:

## Capture

1. open the booth in smartphone landscape;
2. verify that the live preview uses the available viewport effectively;
3. start a capture;
4. verify the countdown remains clearly visible;
5. verify the screen becomes white immediately after countdown;
6. verify `Ne bougez plus` appears in black;
7. verify the white screen is visible before and during the still capture;
8. verify REVIEW replaces the white screen after capture.

## Review and Wi-Fi QR

1. configure a recognizable Wi-Fi network name in Admin;
2. capture a photo;
3. verify the configured network name appears above the QR code;
4. verify the QR remains usable;
5. clear the configured network name;
6. verify the generic Wi-Fi instruction is displayed instead.

## Navigation

Verify that existing behavior remains correct for:

- retake;
- delete;
- print;
- QR download;
- slideshow entry;
- slideshow wake-up;
- recoverable error.

## Landscape

Test at least:

- a desktop browser resized to a smartphone-like landscape aspect ratio;
- the actual smartphone in landscape orientation.

The participant workflow must not require normal page scrolling.

# Expected result

Before editing:

1. inspect the existing participant-facing templates, CSS and JavaScript;
2. summarize the existing UX structure briefly;
3. identify the smallest set of files requiring modification;
4. explain how the white screen will be painted before still capture;
5. identify where `wifi_network_name` belongs in the existing configuration
   model.

Then implement the milestone.

After implementation report only:

- files changed;
- participant layouts changed;
- capture-screen behavior;
- Wi-Fi configuration added;
- QR message behavior;
- Pyright result;
- pytest result;
- manual smartphone validation checklist.

Stop after this milestone.

Do not implement:

- Raspberry Pi-specific UI;
- Wi-Fi access-point configuration;
- Wi-Fi password management;
- RpicamCameraBackend;
- CUPS;
- printer-specific UI;
- new product workflows.