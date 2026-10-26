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
on the network.

---

## 7. Booth configuration

### booth_name

Type:

    str

Example:

    Pierre's Photobooth

Purpose:

Human-friendly booth name displayed where appropriate.

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

### printing_enabled

Type:

    bool

Development default:

    false

### printer_backend

Conceptual type:

    PrinterBackendType

Expected values:

    null
    cups

Development default:

    null

### cups_printer_name

Type:

    str | None

Required only when CUPS printing is enabled.

The configured printer name must be validated against printers reported by
CUPS rather than interpolated into a shell command.

### print settings

Paper size, orientation and printer-specific options should only be added after
real CUPS and Canon Selphy CP740 validation.

Do not encode imaginary printer compatibility into the default
configuration.

---

## 22. Administration configuration

### admin_secret

The admin secret is optional startup configuration stored as
`startup.admin_secret` in the local JSON file. Keep the local `config.json`
uncommitted and restrict access to it on shared systems.

The secret must:

- not be committed;
- not be logged;
- not be included in diagnostics;
- not be returned by health endpoints.

Version 1 only requires lightweight protection suitable for a trusted local
network.

It is not intended to provide Internet-facing authentication.

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

The typed configuration boundary currently implements startup settings for
bind host, port, debug mode, data root, camera backend and the optional admin
secret. Runtime JSON settings are booth name, countdown, idle timeout,
slideshow enabled and slideshow interval. Unsupported or unknown JSON keys are
rejected rather than silently ignored.

Startup settings are read when the Flask application is created and require an
application restart to change their effective values. Booth settings are
persisted separately and do not require a camera restart; an external edit to
the JSON file is picked up on the next application start. A future admin
workflow must publish a changed in-memory value only after its atomic save
succeeds.

Saving writes a validated complete JSON document to a temporary file beside
the destination, flushes it, then replaces the destination atomically. A
failed save leaves the prior destination intact. Invalid JSON, wrong value
types, unknown settings and out-of-range values raise a configuration error;
the invalid source file is preserved. A missing file uses defaults and is not
created until settings are explicitly saved.