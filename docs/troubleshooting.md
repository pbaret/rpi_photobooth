# Troubleshooting

## 1. Raspberry Pi camera diagnostics

The Raspberry Pi camera stack must work on its own before the photobooth
application is involved:

    Raspberry Pi 5 -> Raspberry Pi OS -> rpicam-apps / libcamera -> Camera Module 3

Run the standalone diagnostic script on the Pi as a normal user (no `sudo`,
Flask does not need to be running):

    scripts/pi-diagnostics.sh

It prints `PASS`, `FAIL` and `SKIP` lines and exits `0` only when the mandatory
camera prerequisites pass (rpicam executables present, camera detected, still
capture, bounded video). It never installs software or changes system
configuration. Temporary images go to a private `mktemp` directory, never to the
photobooth gallery, and are deleted on exit. Every rpicam process it starts is
bounded by `-t` and `timeout`.

### Observed reference environment

Validated on 2026-10-31:

| Item | Observed |
|------|----------|
| Board | Raspberry Pi 5 Model B Rev 1.0 |
| OS | Raspberry Pi OS (Debian 13 trixie), image 2026-10-06, `aarch64` |
| Kernel | `6.18.50+rpt-rpi-2712` |
| rpicam-apps | v1.14.0 (`/usr/bin/rpicam-hello`, `rpicam-still`, `rpicam-vid`) |
| libcamera | v0.7.2+rpt20261009 |
| Camera | `imx708_wide` (Camera Module 3 Wide), 4608x2592 10-bit |
| Python / uv | 3.13.5 / 0.13.5 |

### Required executables

The production backend uses only the current `rpicam-*` names:

- `rpicam-hello` (camera listing in diagnostics);
- `rpicam-still` (high-resolution capture);
- `rpicam-vid` (preview).

Legacy `raspistill`, `raspivid`, `libcamera-still` and `libcamera-vid` are not
used. Availability is detected with `command -v <name>`; installation paths are
not assumed. If missing, install manually with `sudo apt install rpicam-apps`.

### Camera detection

    rpicam-hello --list-cameras

A detected camera appears as a numbered line such as
`0 : imx708_wide [4608x2592 10-bit RGGB] (...)` followed by its sensor modes.
Observed imx708 modes: 1536x864 @120 fps (cropped), 2304x1296 @56 fps,
4608x2592 @14 fps.

### Permissions

Camera access requires read/write access to `/dev/media*`, `/dev/video*` and
`/dev/dma_heap/*`, which are owned by group `video`. The default Pi user is a
member of `video`. If it is not, the manual fix is:

    sudo usermod -aG video <user>

then log out and back in. The script reports group membership but never changes
it.

### Manual still diagnostic

    rpicam-still --nopreview --immediate -t 1 -o /tmp/diag.jpg
    file /tmp/diag.jpg
    rm /tmp/diag.jpg

Expected: exit status 0 and a `JPEG image data ... 4608x2592` file (about
1.7 MB). `--nopreview` is required over SSH because there is no display.

### Manual preview/video diagnostic

    timeout 15 rpicam-vid --nopreview -t 2000 --codec mjpeg \
        --width 1280 --height 720 -o - | wc -c

Expected: exit status 0 after about 2 seconds and a non-zero byte count. An
indefinite preview (`-t 0`) is stopped with SIGINT or SIGTERM; both were
observed to terminate the process within a fraction of a second.

### Capabilities observed on the installed tools

Observed in `rpicam-still --help` / `rpicam-vid --help` (v1.14.0):

- autofocus: `--autofocus-mode` (`manual`, `auto`, `continuous`),
  `--autofocus-range` (`normal`, `macro`, `full`), `--autofocus-speed`,
  `--autofocus-window`, `--lens-position`; `--autofocus-on-capture` is
  still-only;
- exposure: `--shutter`, `--gain`, `--ev`, `--metering`, `--exposure`,
  `--flicker-period`, `--hdr`;
- colour/image: `--awb`, `--awbgains`, `--brightness`, `--contrast`,
  `--saturation`, `--sharpness`, `--denoise`;
- transforms: `--hflip`, `--vflip`, `--rotation`;
- sizing: `--width`, `--height`, `--mode`, `--viewfinder-mode`,
  `--quality`, `--framerate`;
- preview transport: `rpicam-vid --codec` (`h264`, `libav`, `mjpeg`,
  `yuv420`), `-o -` for stdout.

Actually exercised on the camera: `--nopreview`, `--immediate`, `-t`, `-o`,
`--autofocus-mode auto --autofocus-on-capture`, `--codec mjpeg`, `--width`,
`--height`, stdout output, SIGINT/SIGTERM termination. All other options are
only *advertised* by the installed tools and are not yet validated against the
camera or mapped to `CameraSettings`.

### Not yet validated

The individual commands work, but the application-level ownership transition
has not been validated:

    rpicam-vid running -> stop -> wait for release -> rpicam-still -> capture
        -> later restart preview

This belongs to the `RpicamCameraBackend` milestone.

## 2. Interpreting failures

### System/hardware failures

These are below the photobooth application boundary; fix the OS, packages,
cabling or permissions, not the application:

- an rpicam executable is missing;
- `rpicam-hello --list-cameras` reports no camera (check the ribbon cable,
  connector orientation and port);
- the camera is inaccessible (permission errors on `/dev/media*` or
  `/dev/video*`, or another process already owns the camera);
- standalone `rpicam-still` or `rpicam-vid` fails or times out.

### Application failures

If `scripts/pi-diagnostics.sh` passes but `RpicamCameraBackend` fails,
investigate the application first:

- command construction (arguments, allowlisted settings mapping);
- subprocess lifecycle (start, signal, wait, timeout handling);
- preview stream parsing (MJPEG frame boundaries on stdout);
- camera ownership transition between `rpicam-vid` and `rpicam-still`;
- settings mapping from `CameraSettings` to rpicam options.
