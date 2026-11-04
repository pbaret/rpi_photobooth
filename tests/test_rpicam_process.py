"""Exercise the real finite-command runner with the Python interpreter as a stand-in.

These tests spawn only ``sys.executable`` so they run on any development
machine without rpicam, while still covering argument-list execution, exit
status reporting, timeout killing and launch failures.
"""

import subprocess
import sys

import pytest

from photobooth.camera.process import (
    FiniteCommandResult,
    ProcessLaunchError,
    ProcessTimeoutError,
    SubprocessCameraProcessRunner,
)


def test_run_reports_exit_status_and_stderr_tail() -> None:
    runner = SubprocessCameraProcessRunner()

    result = runner.run(
        (sys.executable, "-c", "import sys; sys.stderr.write('diag'); sys.exit(3)"),
        timeout=10.0,
    )

    assert result == FiniteCommandResult(returncode=3, stderr_tail="diag")


def test_run_kills_and_reports_timeout() -> None:
    runner = SubprocessCameraProcessRunner()

    with pytest.raises(ProcessTimeoutError):
        runner.run((sys.executable, "-c", "import time; time.sleep(60)"), timeout=0.2)


def test_run_missing_executable_is_launch_error() -> None:
    runner = SubprocessCameraProcessRunner()

    with pytest.raises(ProcessLaunchError):
        runner.run(("/nonexistent/photobooth-missing-binary",), timeout=5.0)


def test_find_executable_returns_none_for_missing_name() -> None:
    runner = SubprocessCameraProcessRunner()

    assert runner.find_executable("photobooth-definitely-not-installed") is None


def test_run_passes_an_argument_list_without_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """A command containing shell metacharacters reaches Popen verbatim, never via a shell."""
    observed: list[tuple[list[str], bool]] = []
    real_popen = subprocess.Popen

    def recording_popen(
        args: list[str], *, stdin: int, stdout: int, stderr: int, shell: bool, close_fds: bool
    ) -> "subprocess.Popen[bytes]":
        """Record the argument object and shell flag, then start the real process."""
        observed.append((args, shell))
        return real_popen(
            args, stdin=stdin, stdout=stdout, stderr=stderr, shell=shell, close_fds=close_fds
        )

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    command = (sys.executable, "-c", "pass", "; echo injected")

    SubprocessCameraProcessRunner().run(command, timeout=10.0)

    assert observed == [(list(command), False)]


def test_verbose_stderr_is_bounded_to_the_newest_tail() -> None:
    """rpicam --verbose=2 output cannot grow the retained diagnostics without limit."""
    script = "import sys; sys.stderr.write('x' * 50000 + 'END'); sys.exit(1)"

    result = SubprocessCameraProcessRunner().run((sys.executable, "-c", script), timeout=10.0)

    assert result.stderr_tail.endswith("END")
    assert len(result.stderr_tail) <= 4096
