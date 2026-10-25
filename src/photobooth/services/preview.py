"""Share one camera preview producer among active HTTP stream clients.

The application factory owns this service for the process lifetime. The
service owns no hardware itself; it starts and stops its injected CameraBackend
and keeps the latest immutable JPEG available to concurrent subscribers.
"""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Condition, Thread
from time import sleep

from photobooth.camera.contract import (
    CameraBackend,
    CameraError,
    CameraUnavailableError,
)


class CaptureInProgressError(Exception):
    """Report that another capture workflow already owns the camera."""


class PreviewService:
    """Manage a shared preview frame and camera lifecycle for browser clients.

    Camera access is performed by one producer thread after the first frame is
    acquired synchronously. A condition protects the latest frame and its
    generation counter. Each subscriber receives that frame and then waits for
    newer generations. The backend is stopped when the last subscriber leaves
    or when the application closes the service.
    """

    def __init__(self, camera: CameraBackend) -> None:
        """Create a stopped preview service around the app-owned backend."""
        self._camera = camera
        self._condition = Condition()
        self._latest_frame: bytes | None = None
        self._generation = 0
        self._subscribers = 0
        self._worker: Thread | None = None
        self._camera_started = False
        self._capturing = False
        self._capture_started = False
        self._error: CameraError | None = None
        self._closed = False

    def subscribe(self) -> "PreviewSubscription":
        """Open a stream and start the camera on demand.

        The first frame is read before returning, so startup and initial frame
        failures can be translated into an HTTP error before stream headers
        are sent. Later clients share the currently published frame.
        """
        with self._condition:
            if self._closed:
                raise CameraUnavailableError("preview service is closed")
            if self._capture_started:
                raise CameraUnavailableError("camera capture is in progress")
            start_worker = self._worker is None
            if start_worker:
                if self._subscribers > 0 and self._error is not None:
                    raise self._error
                if self._camera_started:
                    self._camera.stop()
                    self._camera_started = False
                self._error = None
                self._camera.start()
                self._camera_started = True
                try:
                    self._latest_frame = self._camera.preview_frame()
                except CameraError:
                    self._camera.stop()
                    self._camera_started = False
                    raise
                self._generation += 1
            elif self._error is not None:
                raise self._error
            self._subscribers += 1
            if start_worker:
                self._worker = Thread(
                    target=self._produce_frames,
                    name="photobooth-preview",
                    daemon=True,
                )
                self._worker.start()
            return PreviewSubscription(self, self._generation - 1)

    def capture(self, countdown_seconds: int) -> None:
        """Reserve the camera, wait through the countdown, and capture a still.

        The reservation rejects simultaneous capture requests. Existing
        preview subscribers are ended after the countdown, and the producer
        is joined before the backend is restarted for its exclusive capture.
        Still output is temporary and is discarded when this operation ends;
        callers receive only success or a camera-domain error.
        """
        with self._condition:
            if self._closed:
                raise CameraUnavailableError("preview service is closed")
            if self._capturing:
                raise CaptureInProgressError("a capture is already in progress")
            self._capturing = True
        try:
            sleep(countdown_seconds)
            with self._condition:
                self._capture_started = True
                self._condition.notify_all()
                worker = self._worker
            if worker is not None:
                worker.join()
            with TemporaryDirectory(prefix="photobooth-capture-") as directory:
                with self._condition:
                    if self._closed:
                        raise CameraUnavailableError("preview service is closed")
                    if self._camera_started:
                        self._camera.stop()
                        self._camera_started = False
                    self._camera.start()
                    self._camera_started = True
                try:
                    self._camera.capture(Path(directory) / "capture.jpg")
                finally:
                    with self._condition:
                        self._camera_started = False
        finally:
            with self._condition:
                self._capture_started = False
                self._capturing = False
                self._condition.notify_all()

    def close(self) -> None:
        """Stop production, wait for its camera call, and release the backend.

        An in-progress backend operation must return before shutdown can
        complete. The backend remains responsible for resources if its stop
        operation raises, and this method makes one final cleanup attempt.
        """
        with self._condition:
            self._closed = True
            self._condition.notify_all()
            worker = self._worker
        if worker is not None:
            worker.join()
        with self._condition:
            while self._capturing:
                self._condition.wait()
            if self._camera_started:
                self._camera.stop()
                self._camera_started = False

    def next_frame(self, last_generation: int) -> tuple[bytes, int] | None:
        """Wait for a frame newer than the subscriber's last generation."""
        with self._condition:
            while (
                last_generation == self._generation
                and self._error is None
                and not self._closed
                and not self._capture_started
            ):
                self._condition.wait()
            if self._error is not None or self._closed or self._capture_started:
                return None
            if self._latest_frame is None:
                return None
            return self._latest_frame, self._generation

    def unsubscribe(self) -> None:
        """Release one stream subscription and wake the producer if idle."""
        with self._condition:
            if self._subscribers > 0:
                self._subscribers -= 1
            self._condition.notify_all()

    def _produce_frames(self) -> None:
        """Publish frames until all clients leave or the backend fails."""
        try:
            while True:
                with self._condition:
                    if self._closed or self._capture_started or self._subscribers == 0:
                        break
                try:
                    frame = self._camera.preview_frame()
                except CameraError as error:
                    with self._condition:
                        self._error = error
                        self._condition.notify_all()
                    break
                with self._condition:
                    self._latest_frame = frame
                    self._generation += 1
                    self._condition.notify_all()
                    self._condition.wait(timeout=1 / 15)
        finally:
            with self._condition:
                if self._camera_started:
                    try:
                        self._camera.stop()
                    except CameraError as error:
                        if self._error is None:
                            self._error = error
                    else:
                        self._camera_started = False
                self._worker = None
                self._condition.notify_all()


class PreviewSubscription(Iterator[bytes]):
    """Read shared JPEG frames and release one browser's subscription."""

    def __init__(self, service: PreviewService, generation: int) -> None:
        """Start at the previous generation so the current frame is delivered."""
        self._service = service
        self._generation = generation
        self._closed = False

    def __iter__(self) -> "PreviewSubscription":
        """Return this subscription as its own frame iterator."""
        return self

    def __next__(self) -> bytes:
        """Wait for the next shared JPEG or end after failure or shutdown."""
        if self._closed:
            raise StopIteration
        result = self._service.next_frame(self._generation)
        if result is None:
            self.close()
            raise StopIteration
        frame, self._generation = result
        return frame

    def close(self) -> None:
        """Idempotently release this client's camera-preview subscription."""
        if not self._closed:
            self._closed = True
            self._service.unsubscribe()