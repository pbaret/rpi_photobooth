"""Define application-level print results without exposing CUPS details."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class PrintError(Exception):
    """Report a printer operation failure safe for application handling."""

    def __init__(self, message: str, *, uncertain: bool = False) -> None:
        """Keep participant-safe text and whether the printer may have accepted the job."""
        super().__init__(message)
        self.uncertain = uncertain


class PrintStatus(str, Enum):
    """Describe whether a job was submitted, duplicated, or not physically printed."""

    SUBMITTED = "submitted"
    PLACEHOLDER = "placeholder"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class PrintJobState(str, Enum):
    """Describe a CUPS job state without implying physical output confirmation."""

    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    PRINTER_UNAVAILABLE = "printer-unavailable"


@dataclass(frozen=True)
class PrintResult:
    """Describe a print request using safe status text and an optional CUPS job ID."""

    status: PrintStatus
    queue_name: str | None = None
    job_id: str | None = None
    submitted_at: datetime | None = None
    status_text: str = ""


class PrinterBackend(Protocol):
    """Submit managed image bytes without exposing paths or printer implementation."""

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Submit one image and return its outcome or raise a controlled PrintError."""
        ...