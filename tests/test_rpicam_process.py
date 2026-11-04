"""Exercise the real finite-command runner with the Python interpreter as a stand-in.

These tests spawn only ``sys.executable`` so they run on any development
machine without rpicam, while still covering argument-list execution, exit
status reporting, timeout killing and launch failures.
"""

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
