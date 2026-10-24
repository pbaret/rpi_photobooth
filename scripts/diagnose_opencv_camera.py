"""Probe webcam index 0 through the application's OpenCV camera backend."""

import sys

from photobooth.camera import CameraError, OpenCVCameraBackend


def main() -> int:
    """Acquire webcam 0, read one frame, report dimensions and release it."""
    backend = OpenCVCameraBackend(camera_index=0)
    exit_code = 0
    try:
        backend.start()
        frame = backend.preview_frame()
        print(f"Webcam index 0 opened successfully")
        print(f"Requested resolution: {backend.requested_resolution[0]}x{backend.requested_resolution[1]}")
        effective_resolution = backend.effective_resolution
        if effective_resolution is None:
            raise CameraError("camera stopped before resolution could be reported")
        print(f"Effective resolution: {effective_resolution[0]}x{effective_resolution[1]}")
        print(f"Preview JPEG bytes: {len(frame)}")
    except CameraError as error:
        print(f"Webcam diagnostic failed: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        try:
            backend.stop()
        except CameraError as error:
            print(f"Webcam release failed: {error}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())