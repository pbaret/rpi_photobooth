"""Start the photobooth using its configured bind address and port."""

from photobooth.app import create_app
from photobooth.config import load_configuration


def main() -> None:
    """Load configuration once and run Flask with the selected startup values."""
    configuration = load_configuration()
    app = create_app(configuration)
    app.run(
        host=configuration.startup.bind_host,
        port=configuration.startup.port,
        debug=configuration.startup.debug,
    )


if __name__ == "__main__":
    main()