# Photobooth

A local, touch-first photobooth application built with Flask.

## Development

Install the project and its development tools with uv:

    uv sync

Run the application locally. Startup and booth settings are loaded from
`config.json` in the current working directory; see `config.example.json` for
the available options:

    uv run python -m photobooth

Set `PHOTOBOOTH_ADMIN_SECRET` in the process environment to enable the
protected `/admin` interface. The secret is deployment configuration and is
never stored in `config.json`.

Run the automated checks:

    uv run pyright
    uv run pytest

Probe webcam index 0 manually (requires a connected webcam):

    uv run python scripts/diagnose_opencv_camera.py

On the Raspberry Pi, validate the rpicam camera stack without the application
(see `docs/troubleshooting.md`):

    scripts/pi-diagnostics.sh

## Raspberry Pi installation

On Raspberry Pi OS, install [uv](https://docs.astral.sh/uv/getting-started/installation/),
then install the camera and printer system packages:

    sudo apt update
    sudo apt install rpicam-apps printer-driver-gutenprint

From the repository directory, install the Python dependencies and start the
application:

    uv sync
    uv run python -m photobooth