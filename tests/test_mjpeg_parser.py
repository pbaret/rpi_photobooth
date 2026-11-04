"""Verify that MJPEG byte chunks are split into complete JPEG frames safely."""

from photobooth.camera.mjpeg import MjpegFrameParser

FRAME_ONE = b"\xff\xd8\x01\x02\xff\x00\xff\xd9"
FRAME_TWO = b"\xff\xd8\x09\xff\xd9"


def test_frames_split_across_chunks_are_reassembled() -> None:
    parser = MjpegFrameParser()
    data = FRAME_ONE + FRAME_TWO

    assert parser.feed(data[:5]) == []
    assert parser.feed(data[5:]) == [FRAME_ONE, FRAME_TWO]


def test_frame_marker_split_between_chunks_is_not_lost() -> None:
    parser = MjpegFrameParser()
    end_marker_index = FRAME_ONE.index(b"\xff\xd9")

    assert parser.feed(FRAME_ONE[: end_marker_index + 1]) == []
    assert parser.feed(FRAME_ONE[end_marker_index + 1 :]) == [FRAME_ONE]


def test_junk_before_start_marker_is_discarded() -> None:
    parser = MjpegFrameParser()

    assert parser.feed(b"junk" + FRAME_ONE) == [FRAME_ONE]
    assert parser.discarded_bytes > 0


def test_oversized_unterminated_frame_is_dropped_and_parser_recovers() -> None:
    parser = MjpegFrameParser(max_buffered_bytes=16)

    assert parser.feed(b"\xff\xd8" + b"x" * 32) == []
    assert parser.discarded_bytes > 0
    assert parser.feed(FRAME_TWO) == [FRAME_TWO]
