# Photobooth

A local, touch-first photobooth application built with Flask.

## Development

Install the project and its development tools with uv:

    uv sync

Run the application locally:

    uv run flask --app photobooth.app:create_app run

Run the automated checks:

    uv run pyright
    uv run pytest