# Photobooth

A local, touch-first photobooth application built with Flask.

## Development

Install the project and its development tools with uv:

    uv sync

Run the application locally (startup settings can be supplied with
`PHOTOBOOTH_*` environment variables):

    uv run python -m photobooth

Run the automated checks:

    uv run pyright
    uv run pytest

Probe webcam index 0 manually (requires a connected webcam):

    uv run python scripts/diagnose_opencv_camera.py