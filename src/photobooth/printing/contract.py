"""Define printer operations without exposing a printer implementation."""

from enum import Enum
from typing import Protocol


class PrintError(Exception):
    """Report a printer operation failure safe for application handling."""


class PrintStatus(str, Enum):
    """Describe whether a backend submitted a job or accepted a no-op request."""

    SUBMITTED = "submitted"
    PLACEHOLDER = "placeholder"


class PrinterBackend(Protocol):
    """Accept image bytes for printing without exposing filesystem details."""

    def print_photo(self, image_data: bytes) -> PrintStatus:
        """Submit one image and report its outcome or raise PrintError."""
        ...