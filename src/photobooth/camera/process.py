"""Run external camera executables through a small typed process boundary.

This module is the only place that imports ``subprocess`` for the rpicam
backend. Commands are always argument sequences executed without a shell.
Callers receive protocol objects rather than ``subprocess.Popen`` instances, so
tests can substitute deterministic fakes and the backend logic never depends on
the operating-system process API directly.

Long-running processes own their stdout pipe until ``close`` is called, and
their stderr is drained by a background thread into a bounded tail so a chatty
child cannot block on a full pipe or grow memory without limit.
"""

import io
import shutil
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock, Thread
from typing import IO, Protocol

_STDERR_TAIL_BYTES = 4096
_STDERR_READ_BYTES = 1024
_DRAIN_JOIN_SECONDS = 2.0


class ProcessLaunchError(Exception):
    """Raised when an executable cannot be started at all."""


class ProcessTimeoutError(Exception):
    """Raised when a finite process exceeds its timeout and has been killed."""


@dataclass(frozen=True)
class FiniteCommandResult:
    """Describe how a finite command exited.

    ``stderr_tail`` contains at most the final few kilobytes of diagnostic text
    and is intended for logs, never for image data.
    """

    returncode: int
    stderr_tail: str


class LongRunningProcess(Protocol):
    """Own one child process whose stdout is consumed as a byte stream."""

    def read_output(self, size: int) -> bytes:
        """Return up to ``size`` bytes of stdout, or ``b""`` once stdout reaches EOF.

        Blocks until data or EOF is available. Callers must not invoke this
        concurrently from multiple threads.
        """
        ...

    def poll(self) -> int | None:
        """Return the exit code if the process has exited, otherwise ``None``."""
        ...

    def interrupt(self) -> None:
        """Request graceful termination with SIGINT; does nothing if already exited."""
        ...

    def kill(self) -> None:
        """Forcefully terminate the process; does nothing if already exited."""
        ...

    def wait(self, timeout: float) -> int | None:
        """Wait up to ``timeout`` seconds and return the exit code, or ``None`` if still running."""
        ...

    def stderr_tail(self) -> str:
        """Return the most recent bounded diagnostic text written to stderr."""
        ...

    def close(self) -> None:
        """Release stdout and stderr resources; the process must already have exited."""
        ...


class CameraProcessRunner(Protocol):
    """Create external processes for the rpicam backend.

    Implementations must never invoke a shell and must execute exactly the
    supplied argument sequence.
    """

    def find_executable(self, name: str) -> str | None:
        """Return the resolved executable path for ``name``, or ``None`` if it is not installed."""
        ...

    def start(self, args: Sequence[str]) -> LongRunningProcess:
        """Start a long-running process whose stdout is available for reading.

        Raises ``ProcessLaunchError`` if the process cannot be created.
        """
        ...

    def run(self, args: Sequence[str], timeout: float) -> FiniteCommandResult:
        """Run a finite process and return its exit status.

        Raises ``ProcessLaunchError`` if the process cannot be created and
        ``ProcessTimeoutError`` after killing a process that exceeds ``timeout``
        seconds. The process is always reaped before this method returns.
        """
        ...


class _StderrTail:
    """Drain a child's stderr on a daemon thread, retaining only the newest bytes."""

    def __init__(self, read_chunk: Callable[[int], bytes]) -> None:
        """Attach to a stderr reader that returns available bytes, or ``b""`` at EOF."""
        self._read_chunk = read_chunk
        self._lock = Lock()
        self._data = bytearray()
        self._thread = Thread(target=self._drain, name="rpicam-stderr", daemon=True)

    def start(self) -> None:
        """Begin draining stderr in the background."""
        self._thread.start()

    def join(self, timeout: float) -> None:
        """Wait up to ``timeout`` seconds for the drain thread to reach EOF."""
        self._thread.join(timeout)

    def text(self) -> str:
        """Return the retained stderr tail decoded leniently for diagnostics."""
        with self._lock:
            return bytes(self._data).decode("utf-8", errors="replace").strip()

    def _drain(self) -> None:
        """Read stderr until EOF, discarding everything except the newest bytes."""
        while True:
            try:
                chunk = self._read_chunk(_STDERR_READ_BYTES)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            with self._lock:
                self._data.extend(chunk)
                if len(self._data) > _STDERR_TAIL_BYTES:
                    del self._data[:-_STDERR_TAIL_BYTES]


class _PopenProcess:
    """Adapt a ``subprocess.Popen`` with piped stdout and stderr to LongRunningProcess."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        """Take ownership of a started process whose stdout and stderr are pipes."""
        stdout = process.stdout
        stderr = process.stderr
        if not isinstance(stdout, io.BufferedReader) or stderr is None:
            raise ProcessLaunchError("process pipes were not created")
        self._process = process
        self._stdout: io.BufferedReader = stdout
        self._stderr_stream: IO[bytes] = stderr
        self._stderr = _StderrTail(stderr.read)
        self._stderr.start()

    def read_output(self, size: int) -> bytes:
        """Read available stdout bytes; returns ``b""`` at EOF or after the pipe is closed."""
        try:
            return self._stdout.read1(size)
        except ValueError:
            return b""

    def poll(self) -> int | None:
        """Return the child's exit code without blocking."""
        return self._process.poll()

    def interrupt(self) -> None:
        """Send SIGINT, which rpicam-apps treats as a request to exit cleanly."""
        self._process.send_signal(signal.SIGINT)

    def kill(self) -> None:
        """Send SIGKILL to the child."""
        self._process.kill()

    def wait(self, timeout: float) -> int | None:
        """Wait for exit for up to ``timeout`` seconds."""
        try:
            return self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def stderr_tail(self) -> str:
        """Return the bounded stderr tail collected so far."""
        return self._stderr.text()

    def close(self) -> None:
        """Close stdout and wait briefly for the stderr drain to finish."""
        self._stderr.join(_DRAIN_JOIN_SECONDS)
        self._stdout.close()
        self._stderr_stream.close()


class SubprocessCameraProcessRunner:
    """Create real operating-system processes with list arguments and no shell.

    Instances hold no state and may be shared. Each started process is owned by
    the caller that received it.
    """

    def find_executable(self, name: str) -> str | None:
        """Resolve ``name`` through the operating-system ``PATH``."""
        return shutil.which(name)

    def start(self, args: Sequence[str]) -> LongRunningProcess:
        """Start ``args`` with stdin closed, stdout piped and stderr drained."""
        try:
            process = subprocess.Popen(
                list(args),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
            )
        except OSError as error:
            raise ProcessLaunchError(f"{args[0]} could not be started") from error
        return _PopenProcess(process)

    def run(self, args: Sequence[str], timeout: float) -> FiniteCommandResult:
        """Run ``args`` to completion, killing and reaping it if it exceeds ``timeout``."""
        try:
            process = subprocess.Popen(
                list(args),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
            )
        except OSError as error:
            raise ProcessLaunchError(f"{args[0]} could not be started") from error
        stderr_pipe = process.stderr
        if stderr_pipe is None:
            process.kill()
            process.wait()
            raise ProcessLaunchError("process stderr pipe was not created")
        stderr = _StderrTail(stderr_pipe.read)
        stderr.start()
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            stderr.join(_DRAIN_JOIN_SECONDS)
            raise ProcessTimeoutError(f"{args[0]} exceeded {timeout} seconds") from error
        stderr.join(_DRAIN_JOIN_SECONDS)
        return FiniteCommandResult(returncode=returncode, stderr_tail=stderr.text())
