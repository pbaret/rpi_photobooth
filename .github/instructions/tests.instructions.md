---
description: Rules for automated Python tests
applyTo: "tests/**/*.py"
---

# Test rules

Test code must also use type annotations for test helpers, fixtures and
functions.

Test code must have useful documentation when the purpose or scenario is not
obvious from the test name.

Do not add verbose docstrings that simply repeat a descriptive test name.

Automated tests must not require:

- webcam hardware;
- Raspberry Pi hardware;
- rpicam executables;
- CUPS;
- physical printer;
- Internet connectivity.

Use temporary directories for filesystem tests.

Prefer testing observable behavior over implementation details.

External system boundaries may be replaced with fakes or mocks.

Explicitly exercise cleanup after failures when the tested component owns:

- a process;
- a camera;
- a file;
- another external resource.

For rpicam subprocess tests verify the exact argument list where doing so
protects against command injection or unintended options.

Avoid real sleeps where time can be injected or controlled.