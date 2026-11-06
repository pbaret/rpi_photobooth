"""Provide application-level printer abstractions and CUPS integration."""

from photobooth.printing.contract import (
    PrintError,
    PrintJobState,
    PrintResult,
    PrinterBackend,
    PrintStatus,
)
from photobooth.printing.cups import CupsPrinterBackend
from photobooth.printing.null import NullPrinterBackend
from photobooth.printing.service import PrintingService
from photobooth.printing.settings import PrintingSettings

__all__ = [
    "CupsPrinterBackend",
    "NullPrinterBackend",
    "PrintError",
    "PrintJobState",
    "PrintResult",
    "PrinterBackend",
    "PrintingService",
    "PrintingSettings",
    "PrintStatus",
]