# Toolchain

Do not add OpenCV, Pillow or Raspberry Pi dependencies in this milestone.

Use standard-library typing constructs.

The CameraBackend contract must be fully typed and documented.

# Documentation

For every backend operation, document:

- required backend state;
- state after success;
- state after failure;
- idempotency;
- thread-safety;
- resource ownership;
- exceptions exposed to callers.

The contract must not expose OpenCV, subprocess or Raspberry Pi-specific
types.

# Validation

Use type-checking fixtures or small fake implementations to verify that the
contract is practical.

Run Pyright and the relevant pytest tests.
