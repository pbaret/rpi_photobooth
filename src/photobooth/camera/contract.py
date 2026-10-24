"""Define the typed boundary shared by application code and camera backends.

The contract uses only standard-library types so implementations can isolate
OpenCV, subprocess, and Raspberry Pi details behind this module.
"""

from pathlib import Path
from typing import Protocol


class CameraError(Exception):
    """Base class for camera failures intentionally exposed to callers."""


class CameraUnavailableError(CameraError):
    """Report that the camera cannot be acquired or used in its current state."""


class CameraOperationError(CameraError):
    """Report a camera operation failure other than camera unavailability."""


class CameraBackend(Protocol):
    """Control one camera while keeping implementation details private.

    Implementations own and serialize access to their camera resources. Every
    operation is thread-safe; concurrent calls on one backend are serialized.
    A successful capture releases the camera, leaving preview stopped for
    review. Implementations must not expose backend-specific resource types.
    """

    def start(self) -> None:
        """Acquire the camera and make preview available.

        The backend may be stopped or already started. Success leaves it
        started; calling start repeatedly is idempotent and must not acquire a
        second camera resource. On failure, acquired resources are cleaned up
        and the backend is stopped. The backend owns the acquired resources.
        Raises CameraUnavailableError when the camera cannot be acquired and
        CameraOperationError for other startup failures.
        """
        ...

    def stop(self) -> None:
        """Release all camera resources owned by this backend.

        The backend may be started or already stopped. Success leaves it
        stopped with no owned camera resources. Repeated calls are idempotent.
        On failure, cleanup is attempted; the backend remains responsible for
        any resource it could not release, and callers may retry stop. The
        operation is thread-safe and serialized with other backend calls.
        Raises CameraOperationError if resources cannot be released.
        """
        ...

    def preview_frame(self) -> bytes:
        """Return one JPEG-encoded frame while preview is active.

        The backend must be started. Success leaves it started and retains
        ownership of its camera resources. A call while stopped raises
        CameraUnavailableError without changing state. A read or encoding
        failure raises CameraOperationError after attempting cleanup and
        leaves the backend stopped. Calls are not idempotent because each
        returns a newly acquired frame; they are thread-safe and serialized.
        """
        ...

    def capture(self, output_path: Path) -> None:
        """Capture a JPEG still to a caller-owned temporary path.

        The backend must be started. Success writes the still to output_path
        and leaves the backend stopped, releasing camera resources for review.
        Failure also leaves the backend stopped after cleanup; a partial file
        may remain, and the caller owns its cleanup and publication. Each call
        requests a new capture and is not idempotent. The path and file remain
        caller-owned; the backend must not retain them. Calls are thread-safe
        and serialized. A call while stopped raises CameraUnavailableError;
        capture or write failures raise CameraOperationError.
        """
        ...