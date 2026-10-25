"""Start and cleanly shut down the configured photobooth application."""

from typing import cast

from photobooth.app import create_app
from photobooth.config import load_configuration
from photobooth.services.preview import PreviewService


def main() -> None:
    """Load configuration once and run Flask with the selected startup values."""
    configuration = load_configuration()
    app = create_app(configuration)
    try:
        app.run(
            host=configuration.startup.bind_host,
            port=configuration.startup.port,
            debug=configuration.startup.debug,
        )
    finally:
        preview = cast(PreviewService, app.extensions["photobooth.preview"])
        preview.close()


if __name__ == "__main__":
    main()