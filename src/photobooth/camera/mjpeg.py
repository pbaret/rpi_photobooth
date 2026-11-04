"""Split a raw MJPEG byte stream from rpicam-vid into complete JPEG frames.

rpicam-vid writes back-to-back JPEG images to stdout when configured with the
mjpeg codec. Each image begins with the SOI marker ``FF D8`` and ends with the
EOI marker ``FF D9``. Entropy-coded JPEG data escapes every ``FF`` byte, so the
pair ``FF D9`` cannot occur inside scan data and a first EOI after SOI reliably
delimits a frame.

The parser is deliberately tolerant of truncated or corrupted input: bytes
before the next SOI are discarded, and an unterminated frame that grows beyond
the configured bound is dropped so memory use stays fixed.
"""

_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"
_FF = 0xFF


class MjpegFrameParser:
    """Incrementally extract complete JPEG frames from arbitrary byte chunks.

    The parser owns a bounded internal buffer and is not thread-safe. A single
    reader should feed it in stream order.
    """

    def __init__(self, max_buffered_bytes: int = 8 * 1024 * 1024) -> None:
        """Create a parser that abandons an unterminated frame beyond ``max_buffered_bytes``."""
        if max_buffered_bytes < len(_SOI) + len(_EOI):
            raise ValueError("max_buffered_bytes is too small to hold a JPEG frame")
        self._max_buffered_bytes = max_buffered_bytes
        self._buffer = bytearray()
        self._discarded_bytes = 0

    @property
    def discarded_bytes(self) -> int:
        """Return the total number of input bytes dropped as junk or oversized data."""
        return self._discarded_bytes

    def feed(self, data: bytes) -> list[bytes]:
        """Append ``data`` and return every frame that is now complete, in stream order.

        A trailing ``FF`` byte is retained because it may be the first half of a
        marker that continues in the next chunk.
        """
        self._buffer.extend(data)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(_SOI)
            if start < 0:
                keep = 1 if self._buffer and self._buffer[-1] == _FF else 0
                self._discard(len(self._buffer) - keep)
                break
            if start > 0:
                self._discard(start)
            end = self._buffer.find(_EOI, len(_SOI))
            if end < 0:
                if len(self._buffer) > self._max_buffered_bytes:
                    self._discard(len(self._buffer))
                break
            frame_end = end + len(_EOI)
            frames.append(bytes(self._buffer[:frame_end]))
            del self._buffer[:frame_end]
        return frames

    def _discard(self, count: int) -> None:
        """Remove ``count`` leading bytes from the buffer and record them as dropped."""
        if count <= 0:
            return
        del self._buffer[:count]
        self._discarded_bytes += count
