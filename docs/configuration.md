# Photobooth configuration

## 1. Purpose

This document defines the photobooth configuration model.

The configuration system must support two different concerns:

1. infrastructure and startup configuration;
2. booth settings editable through the administration interface.

These concerns must remain separate because some values are operational or
sensitive while others are intended to be modified by the booth administrator.

---

## 2. Configuration principles

Configuration must be:

- explicit;
- fully typed;
- validated;
- locally persisted where appropriate;
- readable without specialized infrastructure;
- testable without hardware;
- safe against partial writes.

Version 1 does not require:

- a database;
- a configuration server;
- a cloud service;
- a secrets manager.

---

## 3. Configuration sources

Configuration may originate from:

1. application defaults;
2. local JSON configuration file;
3. runtime backend capabilities.

Backend capabilities are not technically configuration values, but they affect
which configured camera values can be used and therefore form part of the
effective configuration model.

---

## 4. Configuration precedence

The application loads defaults, then applies values from `config.json`. The
file defaults to the current working directory and may be supplied explicitly
when calling `load_configuration` in code. Startup options live under
`startup`; booth options live under `booth`. Existing booth-only files remain
readable and are migrated to the sectioned format on the next booth settings
save.

---

## 5. Configuration categories

Configuration is divided into the following logical groups:

- application;
- booth;
- storage;
- preview;
- capture;
- slideshow;
- QR and download;
- camera;
- printing;
- administration.

---

## 6. Application configuration

Application configuration controls the Flask process itself.

Expected settings include:

### bind_host

Type:

    str

Development default:

    127.0.0.1

Purpose:

Controls the network interface on which Flask listens.

Listening on:

    0.0.0.0

must be an explicit operational choice when the booth needs to be reachable by
other devices on the LAN.

### port

Type:

    int

Development default:

    5000

Validation:

    1 <= port <= 65535

### debug

Type:

    bool

Development default:

    false

Debug mode must not be enabled when exposing the application to other devices
on the network. Configuration validation permits debug mode only for
`localhost` or an IP loopback address; wildcard binds and other hostnames or
IP addresses are rejected.

---

## 7. Booth configuration

### booth_name

Type:

    str

Example:

    Pierre's Photobooth

Purpose:

Human-friendly booth name displayed where appropriate.

### wifi_network_name

Type:

    str

Default:

    ""

Purpose:

Display-only Wi-Fi network name shown above the review download QR code. This
setting does not configure wireless networking and does not contain a password.

### countdown_seconds

Type:

    int

Suggested default:

    3

Validation:

    0 <= countdown_seconds <= 30

A zero-second countdown means immediate capture.

### idle_timeout_seconds

Type:

    int

Suggested default:

    120

Validation:

    idle_timeout_seconds >= 0

A value of zero disables inactivity-based slideshow entry.

### slideshow_enabled

Type:

    bool

Suggested default:

    true

---

## 8. Storage configuration

### data_root

Type:

    Path

Suggested default:

    ./data

This is infrastructure-level configuration and should generally not be changed
through the normal booth administration interface.

Application-controlled directories are derived from this root.

Conceptually:

    data/
    ├── photos/
    ├── thumbnails/
    └── metadata/

HTTP clients must never provide these paths.

### minimum_free_space_mb

Type:

    int

Purpose:

Prevents capture attempts when available storage is below an operational safety
threshold.

The exact default should be selected during implementation rather than treated
as a hardware-independent requirement.

---

## 9. Preview configuration

### preview_width

Type:

    int

Purpose:

Requested preview width.

### preview_height

Type:

    int

Purpose:

Requested preview height.

The effective resolution may differ from the requested resolution depending on
the camera backend.

The backend must expose this difference where practical.

The persisted startup section may contain a `camera_settings` object with
boolean, numeric, or string values keyed by stable setting identifiers. The
active backend validates only identifiers it declares. Other entries are
preserved during saves so they can be reused if their owning backend is
selected later; they are not exposed as supported controls while that backend
is inactive.

### preview_mirror

Type:

    bool

Suggested default:

    true

Purpose:

Makes the live preview behave like a mirror.

This setting applies to preview only.

A still photo should not be mirrored by default merely because preview is
mirrored.

### preview_jpeg_quality

Type:

    int

Validation:

    1 <= preview_jpeg_quality <= 100

Purpose:

Controls the size/quality trade-off of MJPEG preview frames where the active
backend supports application-side JPEG quality selection.

---

## 10. Capture configuration

### capture_width

Type:

    int

Purpose:

Requested still-image width.

### capture_height

Type:

    int

Purpose:

Requested still-image height.

### jpeg_quality

Type:

    int

Validation:

    1 <= jpeg_quality <= 100

Purpose:

Requested quality for captured JPEG images when supported.

Requested values must not be confused with backend-confirmed effective values.

---

## 11. Camera backend selection

### camera_backend

Conceptual type:

    CameraBackendType

Expected values:

    synthetic
    opencv
    rpicam

Development default:

    synthetic

A typed enum should represent this setting inside Python.

The application must fail with a useful configuration error for an unknown
backend.

---

## 12. OpenCV configuration

### webcam_index

Type:

    int

Suggested default:

    0

Validation:

    webcam_index >= 0

This value is relevant only when:

    camera_backend == opencv

The application must not fail merely because an OpenCV-only setting exists
while another backend is active.

---

## 13. Camera controls

Camera controls require a capability-driven model.

A configuration file may express requested values, but the application must
distinguish between:

    requested value
          |
          v
    backend capability
          |
          v
    validated value
          |
          v
    applied/effective value

The administrator interface should only offer controls applicable to the active
backend where practical.

Requested settings are persisted as configuration. Backend capabilities and
effective/applied values are runtime status reported by the active backend;
they are not written back as though they were requested values. A setting is
shown as applied only after the backend confirms it. Unsupported or
unconfirmed settings remain distinguishable from successfully applied ones.
Changing a setting that requires a camera or preview restart must not be
reported as effective until that lifecycle transition succeeds.

Concrete backends own their capability declarations and validation
constraints. The admin page uses those declarations to choose native controls
and validates submissions on the server. Read-only capabilities are displayed
as status and cannot be submitted as changes. The app does not restart a
camera implicitly: a restart-required request is persisted as requested,
while the effective value remains the backend's previous readback or unknown
until the backend applies it. OpenCV currently declares preview width, preview
height, and software preview mirroring. Rpicam declares the preview size and
the still-capture controls in section 17a. Synthetic declarations are test
controls, not physical camera capabilities.

Capabilities may carry presentation metadata: a group heading, a unit, a
capture-only flag (the control affects stills but not preview), and an
"active when" condition naming the controlling setting. Backends also check
the complete requested set before it is saved, so rules spanning several
settings are rejected without persisting anything.

---

## 14. Generic camera settings

The domain model should be capable of representing settings such as:

- autofocus mode;
- manual lens position;
- exposure mode;
- exposure time;
- analogue gain;
- exposure compensation;
- automatic white balance;
- colour gains;
- brightness;
- contrast;
- saturation;
- sharpness;
- denoise mode;
- flicker control;
- image transformations.

This list represents the domain configuration vocabulary.

It does not mean that each backend must support every setting.

---

## 15. Unsupported camera controls

If configuration contains a requested setting that the active backend does not
support, the system must not silently claim that it was applied.

The behavior should distinguish between:

- unsupported;
- invalid;
- supported but not currently applicable;
- successfully applied.

The administrator interface should expose this distinction clearly enough for
camera fine-tuning.

---

## 16. Rpicam configuration policy

Rpicam settings must never be represented as a free-form command line.

The following is intentionally prohibited:

    extra_rpicam_arguments = "--whatever ..."

Instead, each supported domain setting has an explicit mapping implemented by
RpicamCameraBackend.

Conceptually:

    CameraSettings
         |
         v
    validated setting
         |
         v
    explicit allowlisted mapping
         |
         v
    subprocess argument list

This prevents configuration from becoming arbitrary command execution.

---

## 17. Rpicam executable configuration

Executable names may default to:

    rpicam-vid
    rpicam-still

If executable paths become configurable, they are infrastructure settings, not
regular admin camera controls.

The backend must diagnose missing executables with a clear domain error.

---

## 17a. Rpicam still-capture settings

`RpicamCameraBackend` declares the following controls under Admin > Camera.
They are persisted as scalar values in `startup.camera_settings`, keyed by the
identifier below. Raw command-line fragments are never stored. Every value is
validated against the bounds below and then mapped to one fixed `rpicam-still`
argument. Options were confirmed against `rpicam-still --help` from
rpicam-apps v1.14.0 (libcamera v0.7.2) on a Raspberry Pi 5 with Camera
Module 3 Wide.

Existing configuration files without these keys keep loading: each missing
key takes the default listed here. Only `jpeg_quality` existed before and its
default changed from `93` to `95`; files that saved it explicitly keep their
value.

Bounds are application bounds, narrower than what rpicam's parser accepts
(it accepts any float for most rendering values). They were chosen for a
photobooth and are documented, not derived from a hardware query.

| Identifier | Type | Unit | Default | Allowed values / bounds | Emitted argument |
|---|---|---|---|---|---|
| `still_width` | integer | px | `4608` | 320–4608, step 2 | `--width N` |
| `still_height` | integer | px | `2592` | 240–2592, step 2 | `--height N` |
| `jpeg_quality` | integer | — | `95` | 50–100 | `--quality N` |
| `denoise` | enum | — | `cdn_hq` | `auto`, `off`, `cdn_off`, `cdn_fast`, `cdn_hq` | `--denoise V` |
| `hdr` | enum | — | `off` | `off`, `auto`, `sensor`, `single-exp` | `--hdr=V` |
| `exposure_control` | enum | — | `auto` | `auto`, `manual` | none (selects shutter/gain emission) |
| `shutter_us` | integer | µs | `16667` | 100–1 000 000 | `--shutter N` (manual exposure only) |
| `gain` | float | × | `4.0` | 1.0–16.0, step 0.1 | `--gain G` (manual exposure only) |
| `metering` | enum | — | `centre` | `centre`, `spot`, `average` | `--metering V` |
| `exposure_mode` | enum | — | `normal` | `normal`, `sport` | `--exposure V` |
| `ev` | float | EV | `0.3` | −2.0–2.0, step 0.1 | `--ev E` |
| `white_balance` | enum | — | `auto` | `auto`, `incandescent`, `tungsten`, `fluorescent`, `indoor`, `daylight`, `cloudy` | `--awb V` (also on preview) |
| `brightness` | float | — | `0.0` | −1.0–1.0, step 0.05 | `--brightness B` |
| `contrast` | float | — | `1.0` | 0.5–2.0, step 0.05 | `--contrast C` |
| `saturation` | float | — | `1.0` | 0.0–2.0, step 0.05 | `--saturation S` |
| `sharpness` | float | — | `1.1` | 0.1–2.0, step 0.05 | `--sharpness S` |
| `autofocus_mode` | enum | — | `auto` | `auto`, `continuous`, `manual` | `--autofocus-mode V` |
| `autofocus_range` | enum | — | `normal` | `normal`, `macro`, `full` | `--autofocus-range V` (auto/continuous only) |
| `autofocus_speed` | enum | — | `fast` | `normal`, `fast` | `--autofocus-speed V` (auto/continuous only) |
| `autofocus_on_capture` | boolean | — | `true` | `true`, `false` | `--autofocus-on-capture` (auto/continuous only) |
| `autofocus_window_x` | float | fraction | `0.2` | 0.0–1.0, step 0.01 | `--autofocus-window x,y,w,h` (auto/continuous only) |
| `autofocus_window_y` | float | fraction | `0.15` | 0.0–1.0, step 0.01 | as above |
| `autofocus_window_width` | float | fraction | `0.6` | 0.01–1.0, step 0.01; `x + width <= 1` | as above |
| `autofocus_window_height` | float | fraction | `0.7` | 0.01–1.0, step 0.01; `y + height <= 1` | as above |
| `lens_position` | float | dioptres | `1.0` (unused) | 0.0–15.0, step 0.05 | `--lens-position P` (manual focus only) |
| `verbosity` | integer | — | `2` | 0–2 | `--verbose=N` |
| `last_still_command` | string | — | — | read-only diagnostic | none |

`preview_size` (`640x480`, `1280x720`, `1920x1080`; default `1280x720`) is the
only preview control and requires a camera restart. All other controls except
`white_balance` affect only the next still and are marked as such in
administration.

There is a single `gain` setting emitted as `--gain`. rpicam's `--analoggain`
is a synonym and is intentionally not exposed.

### Default low-light portrait profile

The defaults target subjects 1–2 m from Camera Module 3 in indoor or
relatively low light, with the smartphone's white CAPTURING screen giving only
limited fill light (it is not a flash). This profile is **provisional**: it
is a starting point, not a measured optimum. Final values need on-site tuning
for room illumination, subject movement, camera position, event background,
the Camera Module 3 standard or wide variant, visible noise, motion blur and
white-balance consistency.

The default still command is:

    rpicam-still --nopreview -t 1 --encoding jpg --quality 95 --width 4608
      --height 2592 --awb auto --metering centre --exposure normal --ev 0.3
      --brightness 0 --contrast 1 --saturation 1 --sharpness 1.1
      --denoise cdn_hq --hdr=off --autofocus-mode auto --autofocus-range normal
      --autofocus-speed fast --autofocus-window 0.2,0.15,0.6,0.7
      --autofocus-on-capture --verbose=2 -o <temporary output>

### Automatic versus manual exposure

With `exposure_control = auto` (default) neither `--shutter` nor `--gain` is
emitted; automatic exposure chooses both, guided by `metering`,
`exposure_mode` and `ev`. Zero is never passed as a stand-in for "automatic".

With `exposure_control = manual` the stored `shutter_us` and `gain` are
emitted. Fixed values can cause underexposure, overexposure, noise or motion
blur when the lighting changes. `metering`, `exposure_mode` and `ev` are still
emitted but have little or no effect once both shutter and gain are fixed.

Shutter and gain stay automatic by default because event lighting is
unpredictable. The trade-off is direct: in low light, automatic exposure
tends to lengthen the shutter (about 60 ms was observed in a dim room), which
blurs moving people; a shorter fixed shutter (for example 16 667 µs) freezes
motion but needs more gain, which adds noise. `exposure_mode = sport` asks
automatic exposure to prefer shorter shutter times.

Inactive values are kept: switching to automatic exposure does not erase the
saved shutter and gain, it only stops emitting them.

### Autofocus interactions

- `auto`: range, speed and window are emitted. With
  `autofocus_on_capture = true`, rpicam scans just before the still. The lens
  position is never emitted.
- `continuous`: range, speed and window are emitted and the lens position is
  never emitted. Because the still is taken almost immediately, continuous AF
  has no time to converge on its own; on rpicam-apps 1.14,
  `--autofocus-on-capture` remains valid and switches to a triggered scan,
  so it is still emitted when enabled.
- `manual`: only `--lens-position` is emitted. Range, speed, window and
  autofocus-on-capture are ignored (not emitted) even if stored.

`lens_position` is a reciprocal distance in dioptres: `0` is infinity, `1.0`
is 1 m, `0.5` is 2 m. It is effectively unset unless the mode is `manual`.

`--immediate` skips rpicam-still's viewfinder phase, and rpicam-apps 1.14 runs
the autofocus-on-capture scan only in that phase. The backend therefore omits
`--immediate` whenever `--autofocus-on-capture` is emitted. On the test Pi
this added about 0.45 s of capture latency (≈0.7 s → ≈1.2 s); with
`--immediate` the lens did not move.

Administration hides controls that the selected mode ignores. This is a
convenience only; the server validates every submission and the command
builder decides what to emit.

### Autofocus window coordinates

The window is a normalized rectangle with origin at the image's top-left
corner: `x` and `y` are the left and top edges as fractions of the image
width and height, `width` and `height` extend right and down. It must satisfy
`0 <= x <= 1`, `0 <= y <= 1`, `0 < width <= 1`, `0 < height <= 1`,
`x + width <= 1` and `y + height <= 1`. The default `0.2,0.15,0.6,0.7` covers
the central area where faces usually are. Out-of-frame rectangles are
rejected before saving; the backend also refuses to build a command with one.

### HDR limitations

All four values are accepted by rpicam-apps 1.14, but acceptance is not proof
of support. On the test Camera Module 3 Wide, only `single-exp` (PiSP
multi-frame HDR on Raspberry Pi 5) reported an HDR mode in capture metadata
and changed exposure; `auto` and `sensor` exited successfully with no
observable HDR effect. HDR can add capture latency, cause ghosting on moving
subjects, change exposure behavior and depends on the sensor and ISP. The
photobooth default is `off`.

### Requested versus effective values

Administration shows the requested value; for rpicam controls the effective
value is "Not reported". The backend can confirm the argument it emitted and
whether `rpicam-still` exited successfully, which the read-only
`last_still_command` diagnostic shows (with the temporary output path replaced
by `<temporary-output>`). A successful exit does not prove that brightness,
autofocus, gain or HDR had the intended photographic effect.

### Command logging

Immediately before each still, the backend logs the full argument list at
INFO level on the `photobooth.camera.rpicam` logger using `shlex.join`. The
logged string is for reading only; the subprocess still receives the original
argument list with `shell=False`. Logged values are validated settings and an
application-controlled temporary path; no secret or download token is
included. `--verbose=2` makes rpicam chatty, but only a bounded stderr tail is
kept, and it is logged only when the command fails.

---

## 18. Slideshow configuration

### slideshow_enabled

Type:

    bool

### idle_timeout_seconds

Type:

    int

### slideshow_interval_seconds

Type:

    int

Suggested behavior:

Defines how often the browser advances to the next slideshow photo.

Validation:

The value must be positive when slideshow is active.

The slideshow uses thumbnails instead of original full-resolution files.

The browser resets inactivity after pointer, keyboard, and wheel activity on
both the booth preview and photo review screens. The booth timer runs only
while IDLE; countdown and capture use independent workflow timing. While
slideshow is active, the first interaction is consumed; waking from review
returns to the live booth preview. The thumbnail list is refreshed on
slideshow entry and once per minute while active; an empty gallery shows the
wake instruction and follows the same refresh schedule. Each fetched
thumbnail list is shuffled client-side before rotation, with an unchanged
chronological sequence avoided.

---

## 19. QR configuration

### public_base_url

Type:

    str | None

Development default:

    None

Examples:

    http://192.168.1.42:5000
    http://photobooth.local:5000

Purpose:

Provides the externally reachable application origin inserted into QR download
URLs.

Set this to the address that a second device on the same LAN can reach,
including the application's port. The configured value must be an HTTP(S)
origin without credentials, a path, query, or fragment. For example:

    http://192.168.1.42:5000

The system must not silently generate:

    http://localhost:5000/...

for a QR code intended to be scanned by another device.

If `public_base_url` is not configured, the review screen remains available but
shows a clear configuration error and does not issue a download token. Invalid
configured values are rejected during configuration loading.

---

## 20. Download token configuration

### download_token_lifetime_seconds

Type:

    int

Default:

    3600

Purpose:

Defines the token lifetime in seconds. The value must be positive. Expiration
is evaluated against the persisted UTC expiration time when a download is
requested; no background cleanup is required.

Token records are owned by DownloadService and stored as JSON beneath
`data_root/metadata/download_tokens`. Tokens are generated using
`secrets.token_urlsafe`, are independent from photo IDs, and each references
exactly one photo. Revocation is persisted in the token record. A token becomes
unusable after expiry, revocation, or deletion of its photo. The download
endpoint checks GalleryService on every request, so deletion revokes access
even if the token record remains on disk.

Download URLs are bearer capabilities: anyone who obtains one can download the
photo until it expires, is revoked, or the photo is deleted. Use only on a
trusted local network; this milestone does not provide authentication or
encrypted transport. Do not expose the application to an untrusted network.

---

## 21. Printing configuration

The optional `printing` JSON object is loaded with documented defaults when it
is missing, so earlier valid configuration files remain compatible. The
development backend defaults to `null`; select `cups` and a queue in protected
Admin > Printing to submit jobs.

| Setting | Default | CUPS option |
|---------|---------|-------------|
| `enabled` | `true` | Application gate |
| `backend` | `null` | Application backend (`null` or `cups`) |
| `queue_name` | `""` | `lp -d` destination |
| `page_size` | `Postcard` | `PageSize` |
| `color_model` | `RGB` | `ColorModel` |
| `resolution` | `300dpi` | `Resolution` |
| `image_type` | `Photo` | `StpImageType` |
| `borderless` | `true` | `StpBorderless` |
| `page_fit` | `Shrink` | `StpiShrinkOutput` |
| `color_precision` | `Normal` | `StpColorPrecision` |
| `color_correction` | `None` | `StpColorCorrection` |
| `legacy_dyesub_gamma` | `false` | `StpLegacyDyesubGamma` |
| `brightness` | `null` (neutral) | `StpBrightness=None` |
| `contrast` | `null` (neutral) | `StpContrast=None` |
| `saturation` | `null` (neutral) | `StpSaturation=None` |
| `gamma` | `null` (neutral) | `StpGamma=None` |

Page, color, precision, correction and layout controls use application
allowlists intersected with choices reported for the selected queue.
Brightness, contrast, saturation and gamma accept only the driver's discrete
integer values; `Custom.REAL` and channel-level controls are not exposed.
Python `null` represents neutral in configuration and is deliberately mapped
to the Gutenprint literal `None` when submitted.

The configured queue is validated against `lpstat`; the safe queue name is
passed as one command argument. Every selected CUPS option and value must be
reported by `lpoptions -p <queue> -l`. CUPS command failures are bounded and
translated to participant-safe messages. CUPS job completion is not proof of
physical output.

The target profile is validated for a Canon SELPHY CP1000 with Gutenprint.
Queue creation and operating-system package installation remain explicit
deployment prerequisites and are not performed by the application.

---

## 22. Administration configuration

### admin_secret

The optional secret is supplied through the `PHOTOBOOTH_ADMIN_SECRET` process
environment variable. It is deployment configuration and is not loaded from or
written to the runtime JSON file. Legacy `startup.admin_secret` JSON values are
ignored.

The `/admin` interface uses HTTP Basic authentication with the fixed username
`admin` and a constant-time password comparison. This is lightweight
protection for normal booth users on a trusted local network, not
Internet-facing authentication. Use a protected transport on untrusted
networks. The secret must:

- not be committed;
- not be logged;
- not be included in diagnostics;
- not be returned by health endpoints.

Admin updates validate the complete candidate using the existing typed
configuration models, then use the shared atomic JSON persistence operation.
Failed validation or persistence leaves prior settings active. Booth settings,
the public download origin, and token lifetime apply immediately. Changing the
camera backend is persisted but requires an application restart; it is not
reported as active before restart.

Diagnostics expose only active and saved camera backend names, managed photo
count, configured public base URL, and printer backend class. They omit
secrets, tokens, filesystem paths, environment variables, raw subprocess
output, and camera status not available through the current backend contract.

---

## 22a. Event theme

### Ownership and file

The participant look of an event is stored separately from startup and booth
settings, in `theme.json` beside `config.json` (same directory, fixed name).
`photobooth.theme` owns the typed model (`ThemeSettings`), parsing,
persistence and the mapping to CSS. Shared colors and layouts are separate
from the independently configured PREVIEW, REVIEW and SLIDESHOW backgrounds.
A missing file means the default theme;
the file is created only when the admin appearance form is saved. To switch
events, replace `theme.json` and reload the booth page, or save the admin
form. Changes saved through the admin apply on the next participant page
load; no restart is required.

The file is local deployment state and is ignored by Git. Examples live in
`docs/themes/`:

- `default.json`: the built-in defaults;
- `artwork.json`: light palette, preview on the right, capture bottom-left,
  title hidden, so artwork on the left stays visible;
- `alternate-review.json`: dark palette, centered compositions, QR left,
  actions right.

### Defaults and partial files

Every section and key is optional. Absent values use the model defaults, so
a file that only sets `colors.primary` is valid. Unknown sections or keys,
wrong JSON types and values outside the allowlists are rejected with an
error naming the dotted path (for example `preview.size`). A malformed theme
file prevents startup, as `config.json` does.

### Structure

    {
      "colors": {
        "surface": "#1f2328",
        "foreground": "#f5f1e8",
        "primary": "#f2b544",
        "primary_text": "#15171a"
      },
      "preview_background": {
        "color": "#111316", "image": null, "fit": "cover", "position": "center"
      },
      "review_background": {
        "color": "#111316", "image": null, "fit": "cover", "position": "center"
      },
      "slideshow_background": {
        "color": "#111316", "image": null, "fit": "cover", "position": "center"
      },
      "preview": {
        "position": "left", "size": "large", "fit": "contain",
        "capture_position": "right",
        "title_visible": true, "title_position": "top-right"
      },
      "review": {
        "photo_position": "left", "photo_size": "medium",
        "qr_position": "top-right", "actions_position": "bottom-right"
      }
    }

### Colors

Each color must match `#rrggbb` exactly; names, short forms, `rgb()` and any
other CSS text are rejected. `primary_text` is drawn on `primary` (the capture
button and main actions); `foreground` is drawn on each screen background and
on `surface` (panels). Contrast is the event designer's responsibility. Some elements
deliberately ignore the palette:

- the countdown disc (white on translucent black);
- the white QR plate;
- the destructive red of `Supprimer`;
- the white CAPTURING screen.

### Screen backgrounds

`preview_background`, `review_background` and `slideshow_background` each own
their `color`, optional `image`, `fit` and `position`. These settings affect
only that screen; shared button colors, typography and layout settings remain
in the common theme. PREVIEW includes IDLE and COUNTDOWN. REVIEW applies to the
dedicated photo review page. SLIDESHOW changes the surface behind slideshow
thumbnails without replacing the displayed photo.

Each `image` is `null` or the identifier of an image managed by
`BackgroundService` (22 URL-safe characters plus `.jpg` or `.png`). Paths and
URLs cannot be expressed. Images are added through the corresponding admin
screen-background upload field:

1. the bytes are decoded with Pillow (JPEG, PNG or WebP, at most 40 MP);
2. EXIF orientation is applied and the longest edge is limited to 3840 px;
3. the result is re-encoded (PNG if transparent, otherwise JPEG);
4. it is published atomically under `data_root/backgrounds/<random id>`.

The client filename is ignored. A successful upload becomes the selected
background for that screen. Previously uploaded images remain selectable and
one managed image may be selected by multiple screens. Images are immutable;
changing a screen's selection does not delete or alter an image that another
screen still uses. Request bodies are limited to 25 MB.

If a configured file has been removed from storage, only the affected screen
falls back to its own `color`.

`fit` is `cover` or `contain`. `position` is one of `center`, `top`,
`bottom`, `left`, `right`, `top-left`, `top-right`, `bottom-left`,
`bottom-right`.

### Backward compatibility

Themes written before per-screen backgrounds used `colors.background` and a
single `background` object containing `image`, `fit` and `position`. They
continue to load: the old color and image settings initialize PREVIEW, REVIEW
and SLIDESHOW alike. Saving the migrated theme writes three explicit
`*_background` objects and removes the legacy fields. Other shared colors and
PREVIEW/REVIEW layouts are preserved. In a new-format theme, an omitted
screen-background section uses its normal default.

CAPTURING intentionally does not use any event background. Its full-screen
white panel is supplemental camera light, with the black “Ne bougez plus”
message; configurable backgrounds must never cover this state.

### Semantic layout

PREVIEW and REVIEW share one model:

- a dominant hero (live preview or photograph) with a horizontal `position`
  (`left`, `center`, `right`);
- a `size` (`small`, `medium`, `large`, `full`) that selects a share of the
  usable width (50 %, 64 %, 76 %, 100 %);
- the hero is always capped by the available height and its aspect ratio,
  so no value can push it off screen;
- widgets use anchors: `top-left`, `top-center`, `top-right`, `left`,
  `right`, `bottom-left`, `bottom-center`, `bottom-right`;
- side anchors center the widget in the free column beside the hero; when
  that column is too narrow, the widget overlaps the hero at a minimum width
  and stays on top;
- `*-center` anchors span the stage width at its top or bottom;
- a fully centered anchor does not exist.

PREVIEW (`preview`) adds:

- `fit`:
  - `contain` frames the camera at its own aspect ratio;
  - `cover` fills the full stage height and crops the camera image;
- `capture_position`: where the round capture button goes;
- `title_visible` and `title_position`: the booth name.

A visible title cannot share the capture button's anchor. COUNTDOWN reuses
this composition with the countdown drawn over the preview.

REVIEW (`review`) uses `photo_position`, `photo_size`, `qr_position` (QR code
and Wi-Fi instruction) and `actions_position` (`Nouvelle Photo`, `Imprimer`,
`Supprimer`). The two panels may share a side column only as top and bottom,
and a `*-center` panel cannot share its row with the other panel. Other
combinations are rejected because they can overlap on a landscape phone.

### Mapping to CSS

`ThemeSettings.css_variables()` emits the shared palette and validated
screen-specific color, fit and position properties:

- `--booth-surface-color`;
- `--booth-foreground-color`;
- `--booth-primary-color`;
- `--booth-primary-text-color`;
- `--booth-{preview|review|slideshow}-background-color`;
- `--booth-{preview|review|slideshow}-background-fit`;
- `--booth-{preview|review|slideshow}-background-position`.

When a screen's image exists, the booth Blueprint adds that screen's
`--booth-{screen}-background-image` property with its managed media URL.
`participant.css` shares the common backdrop rendering rules and each
participant element selects its screen-specific values.

Layout enums become fixed classes:

- `hero-{position}`, `hero-size-{size}` and `hero-fit-{fit}` on the stage;
- `anchor anchor-x-{left|center|right} anchor-y-{top|middle|bottom}` on each
  widget container.

`static/participant.css` turns these into geometry. Templates never receive
configured text as CSS.

---

## 23. Runtime configuration file

Default location:

    config.json

The application reads startup and booth configuration from this file. A
`config.example.json` template is provided. The local config file is ignored by
Git so deployment-specific settings and secrets are not accidentally committed.

The file must not contain:

- arbitrary shell commands;
- arbitrary rpicam arguments.

---

## 24. Atomic configuration persistence

Configuration writes must be atomic.

Expected sequence:

1. serialize and validate the complete new configuration;
2. write to a temporary file in the appropriate filesystem;
3. flush/close the file;
4. atomically replace the destination.

If serialization or writing fails, the previously valid configuration should
remain available.

The implementation should avoid partially written JSON becoming the active
configuration.

---

## 26. Invalid configuration file

If the persisted JSON file is malformed:

- do not silently overwrite it;
- do not silently fall back and make the corruption invisible;
- report a clear configuration error;
- preserve the original file for diagnosis.

Recovery behavior should be explicit.

---

## 27. Missing configuration file

If no runtime configuration file exists:

- use application defaults;
- do not consider this an error;
- create the persistent file only when persistence is actually required.

---

## 28. Configuration validation

Validation takes place before values are committed.

Examples:

- ports must be valid;
- dimensions must be positive;
- JPEG quality must be within its accepted range;
- countdown must not be negative;
- webcam index must not be negative;
- backend names must be known;
- slideshow interval must be valid;
- URLs must satisfy the expected application URL contract;
- camera controls must be validated against backend capabilities before
  application.

Validation errors should identify the relevant setting.

---

## 29. Restart-required settings

Some settings can be applied immediately.

Others may require:

- camera restart;
- preview restart;
- application restart.

The configuration model should represent this distinction.

The administration interface should not pretend that a new value is active
before the required lifecycle transition has occurred.

---

## 30. Configuration API model

Application code should work with typed configuration objects rather than raw
JSON dictionaries.

Conceptually:

    ApplicationConfig
    BoothConfig
    StorageConfig
    CameraConfig
    SlideshowConfig
    DownloadConfig
    PrintingConfig

The exact dataclass grouping should remain pragmatic.

Do not create one class per individual configuration value.

---

## 31. Typing

All configuration structures must be completely typed.

Avoid:

    dict[str, Any]

as the primary application-level configuration representation.

Raw decoded JSON necessarily begins as dynamically typed external data.

That dynamic data must be validated and converted at the configuration
boundary into precise application types.

Unavoidable `Any` or unknown values must not propagate beyond that boundary.

---

## 32. Configuration documentation

Every configuration model must document:

- its responsibility;
- defaults;
- validation rules;
- persistence behavior;
- whether values are editable;
- whether changes apply immediately;
- whether a hardware restart is required.

Individual fields require documentation when their meaning, units or behavior
is not obvious from their type and name.

---

## 33. Testing requirements

Configuration tests must not require hardware.

At minimum test:

- default configuration;
- missing file;
- valid persisted configuration;
- malformed JSON;
- unknown backend;
- invalid numeric bounds;
- environment overrides;
- secret separation;
- atomic persistence;
- failed persistence;
- camera settings independent of active hardware;
- conversion from external JSON data to typed configuration.

Tests must run with pytest.

The configuration implementation must pass Pyright.

---

## 34. Initial development configuration

A practical PC development configuration should conceptually resemble:

    camera_backend = synthetic
    printer_backend = null
    printing_enabled = false
    countdown_seconds = 3
    slideshow_enabled = true
    public_base_url = none

This allows initial startup without any physical hardware.

For webcam development, only the necessary setting changes:

    camera_backend = opencv
    webcam_index = 0

Raspberry Pi deployment later changes the relevant infrastructure selection:

    camera_backend = rpicam
    printer_backend = cups

No Flask route or application service should need modification when switching
between these configurations.

---

## 35. Configuration evolution rule

Do not add a setting merely because an underlying library exposes an option.

A setting belongs in application configuration only when:

1. it corresponds to a useful photobooth behavior;
2. its semantics can be documented;
3. its values can be validated;
4. at least one backend can meaningfully implement it.

Backend-specific diagnostic details may remain backend internals instead of
becoming user configuration.

## 36. Initial implementation behavior

The typed configuration boundary implements startup settings for bind host,
port, debug mode, data root, camera backend, public base URL, and download-token
lifetime. The admin secret is sourced separately from
`PHOTOBOOTH_ADMIN_SECRET`. Runtime JSON also stores booth name, countdown, idle
timeout, slideshow enabled, and slideshow interval. Unsupported or unknown
JSON keys are rejected rather than silently ignored.

The application factory loads settings once. Admin updates publish new
request-time booth and download settings only after atomic persistence
succeeds. Those values take effect immediately; camera backend selection is
persisted but takes effect only after an application restart. A process restart
loads all persisted settings from the JSON file.

Saving writes a validated complete JSON document to a temporary file beside
the destination, flushes it, then replaces the destination atomically. A
failed save leaves the prior destination intact. Invalid JSON, wrong value
types, unknown settings and out-of-range values raise a configuration error;
the invalid source file is preserved. A missing file uses defaults and is not
created until settings are explicitly saved.