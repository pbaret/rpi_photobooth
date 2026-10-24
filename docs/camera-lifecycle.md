# Camera lifecycle

## 1. Ownership and contract

`CameraBackend` is the application-facing camera boundary. The selected
backend owns the camera handle and any process it starts. Application services
own workflow state and the controlled temporary output path passed to
`capture`; they validate and publish captured images. Routes do not start,
stop, or otherwise control camera hardware directly.

Only one application service may perform a capture workflow at a time. A
backend serializes access to its non-thread-safe resources. Implementations
must not expose OpenCV objects, subprocess handles, file descriptors, or
Raspberry Pi-specific objects through the camera contract.

`start()` and `stop()` are idempotent. Stopping an already stopped backend is
valid. Operations that require a started backend report a domain-level
unavailable or operation failure rather than leaking implementation errors.
The typed signatures and caller-visible exception classes are defined by
`photobooth.camera.CameraBackend`, `CameraUnavailableError`, and
`CameraOperationError`. The contract returns JPEG bytes for a preview frame
and writes a JPEG still to the caller-provided temporary path; capture leaves
the backend stopped for review.

## 2. OpenCV backend

`OpenCVCameraBackend` owns its `VideoCapture` instance from successful open
until release. Importing the module does not open a webcam. `start()` opens the
configured device and reports unavailability if it cannot be opened. Preview
frame reads and capture use the same device and are serialized so they cannot
concurrently operate on `VideoCapture`.

`stop()` releases the device and clears the backend's active state. It is safe
to call repeatedly. If a read, capture, or device open fails, the backend
returns a documented camera failure; cleanup releases any acquired handle.
Returning from review or recovering from ERROR starts the backend again as
part of returning to booth-ready mode.

## 3. Synthetic backend

`SyntheticCameraBackend` uses no physical device or external process. Pillow
renders a fixed 640-by-480 RGB scene and encodes it as JPEG for both preview
and still capture. The scene's pixels are deterministic: repeated preview
frames and captures depict the same content, with no clock, randomness, or
external input. JPEG bytes are guaranteed to decode as JPEG, but their exact
byte sequence is not an API guarantee across Pillow or encoder versions.

The backend follows the observable `CameraBackend` lifecycle: repeated start
and stop are safe, preview requires a started backend, and capture writes a
JPEG to the caller's path then leaves the backend stopped for review. Calls on
one instance are serialized. It is intended for automated tests and
hardware-free UI development; tests must not depend on timing sleeps or
nondeterministic image content. Unlike real hardware, it does not exercise
device acquisition, sensor output, autofocus, exposure, camera contention, or
hardware-specific failures. Pillow is isolated to this backend and shared
image-validation boundaries.

## 4. Rpicam backend

`RpicamCameraBackend` owns the child processes it starts. `rpicam-vid` is the
long-lived preview process and owns the camera while booth-ready preview is
active. Preview output is adapted to the backend's byte-frame contract; the
transport details are an implementation choice and must not change ownership
or lifecycle guarantees. `rpicam-still` is a finite child process used for
still capture.

Commands are argument lists, never shell strings. Camera settings are
validated and mapped through an explicit allowlist. The backend does not
accept arbitrary command-line arguments. The Python environment does not
depend on Picamera2 or other Raspberry Pi camera bindings; the production
operating system still requires rpicam-apps and libcamera.

### Ready and preview

On entry to booth-ready mode, the application starts the backend and
`rpicam-vid`. A successful start establishes preview ownership. Repeated start
does not create a second preview process. A startup error is returned through
the camera contract and the workflow enters ERROR.

### Preview-to-capture transition

After an accepted capture request and countdown:

1. The capture service asks the backend to stop preview.
2. The backend requests graceful termination of `rpicam-vid` and waits for it
   to exit before continuing.
3. If graceful termination exceeds its bounded wait, the backend terminates
   the child forcefully and waits again. It does not start still capture until
   the preview child is confirmed terminated.
4. The backend runs `rpicam-still` as a finite operation with an explicit
   timeout and writes only to the service-provided temporary path.
5. The backend validates process success sufficiently to report capture
   failure; the service validates the resulting JPEG, then publishes it and
   creates its metadata and thumbnail.
6. On success the workflow enters REVIEW. Preview stays stopped for the
   entire review period.

Returning from REVIEW or ERROR to booth-ready operation, including a retake,
starts preview again. Preview and still capture are never intentionally run
concurrently against the same camera.

### Shutdown and failure

Application shutdown calls backend `stop()`. For a live preview child, stop
requests graceful termination, waits, force-terminates only if needed, then
waits again before returning. Repeated stop is harmless. No owned child may be
left running after successful shutdown. Cleanup is attempted even when startup,
preview, capture, or image validation fails.

Still-capture timeouts and non-zero exits become domain-level camera
operation failures. Missing executables and camera-unavailable failures are
reported without leaking raw subprocess exceptions to routes. A failed capture
does not publish an image: the service removes its temporary output and enters
ERROR after cleanup. Preview is not automatically restarted while the
workflow remains in ERROR; a retry or explicit return to booth-ready mode
performs the restart. Failure to terminate a child is reported as a cleanup
failure and remains visible to diagnostics.

All finite subprocess operations have explicit timeouts. The timeout and
termination grace periods are bounded configuration or implementation
constants, not values supplied by HTTP clients.

## 5. Concurrency and testing

The application service rejects duplicate or concurrent capture requests.
Backend operations that touch a camera or process are serialized. The
application factory owns the backend instance and initiates its shutdown;
routes and browser clients do not own backend resources.

Automated tests run without camera hardware or rpicam executables. Service
tests inject `SyntheticCameraBackend` or a fake `CameraBackend`. Rpicam tests
replace the subprocess boundary with a fake and cover preview startup and
shutdown, repeated stop, capture ordering, timeout, non-zero exit, missing
executable, invalid settings and output, and cleanup after exceptions.
OpenCV tests replace the device boundary rather than opening a real webcam.
Real camera acquisition, preview performance, autofocus, and
preview-to-still latency require validation on the Raspberry Pi and Camera
Module 3.