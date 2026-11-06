"""Run finite CUPS commands with bounded output and deterministic timeouts."""

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Thread
from typing import IO, Protocol

_OUTPUT_LIMIT_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 4096


class PrintProcessLaunchError(Exception):
    """Report that a CUPS executable could not be started."""


class PrintProcessTimeoutError(Exception):
    """Report that a CUPS command timed out after its child was reaped."""


@dataclass(frozen=True)
class PrintCommandResult:
    """Contain a finite command result with bounded decoded output."""

    returncode: int
    stdout: str
    stderr: str


class PrintProcessRunner(Protocol):
    """Resolve and run finite external commands without a shell."""

    def find_executable(self, name: str) -> str | None:
        """Return the resolved executable path, or ``None`` if it is unavailable."""
        ...

    def run(self, args: Sequence[str], timeout: float) -> PrintCommandResult:
        """Run an argument list, bound both outputs, and reap a timed-out child."""
        ...


class _BoundedStream:
    """Drain one child pipe while retaining no more than a fixed byte limit."""

    def __init__(self, stream: IO[bytes]) -> None:
        """Take ownership of a pipe reader and prepare its bounded collector."""
        self._stream = stream
        self._data = bytearray()
        self._thread = Thread(target=self._collect, daemon=True)

    def start(self) -> None:
        """Start draining the pipe before the parent waits for process exit."""
        self._thread.start()

    def join(self) -> None:
        """Wait for the pipe to reach EOF after the child has exited."""
        self._thread.join()

    def text(self) -> str:
        """Return retained output decoded without leaking undecodable bytes."""
        return bytes(self._data).decode("utf-8", errors="replace").strip()

    def _collect(self) -> None:
        """Drain all bytes, retaining only the first bounded portion."""
        while True:
            try:
                chunk = self._stream.read(_READ_CHUNK_BYTES)
            except OSError:
                return
            if not chunk:
                return
            remaining = _OUTPUT_LIMIT_BYTES - len(self._data)
            if remaining > 0:
                self._data.extend(chunk[:remaining])


class SubprocessPrintProcessRunner:
    """Execute finite CUPS commands as argument arrays with ``shell=False``."""

    def find_executable(self, name: str) -> str | None:
        """Resolve a command through the operating-system PATH."""
        return shutil.which(name)

    def run(self, args: Sequence[str], timeout: float) -> PrintCommandResult:
        """Run ``args`` with bounded output, killing and reaping on timeout."""
        if not args:
            raise ValueError("a command argument list must not be empty")
        if timeout <= 0:
            raise ValueError("command timeout must be positive")
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
            raise PrintProcessLaunchError(f"{args[0]} could not be started") from error
        if process.stdout is None or process.stderr is None:
            process.kill()
            process.wait()
            raise PrintProcessLaunchError("command output pipes were not created")
        stdout = _BoundedStream(process.stdout)
        stderr = _BoundedStream(process.stderr)
        stdout.start()
        stderr.start()
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            stdout.join()
            stderr.join()
            process.stdout.close()
            process.stderr.close()
            raise PrintProcessTimeoutError(
                f"{args[0]} exceeded its {timeout:g}-second timeout"
            ) from error
        stdout.join()
        stderr.join()
        process.stdout.close()
        process.stderr.close()
        return PrintCommandResult(returncode, stdout.text(), stderr.text())
