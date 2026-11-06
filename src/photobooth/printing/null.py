"""Implement development printing without contacting a physical printer."""

from photobooth.printing.contract import PrintResult, PrintStatus


class NullPrinterBackend:
    """Accept print requests as a predictable no-op for local development."""

    def print_photo(self, image_data: bytes, idempotency_key: str) -> PrintResult:
        """Discard bytes and report that no physical print job was submitted."""
        del image_data
        del idempotency_key
        return PrintResult(
            status=PrintStatus.PLACEHOLDER,
            status_text="Printing is not configured on this device.",
        )