"""Implement development printing without contacting a physical printer."""

from photobooth.printing.contract import PrintStatus


class NullPrinterBackend:
    """Accept print requests as a predictable no-op for local development."""

    def print_photo(self, image_data: bytes) -> PrintStatus:
        """Discard bytes and report that no physical print job was submitted."""
        del image_data
        return PrintStatus.PLACEHOLDER