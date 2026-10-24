# Toolchain

Add Pillow as a runtime dependency.

Use Pillow only behind the synthetic camera and shared image-validation
boundaries.

# Documentation

Document:

- synthetic camera lifecycle;
- deterministic versus variable image content;
- image format guarantees;
- intended testing use;
- differences from real hardware.

# Validation

Test:

- start;
- repeated start;
- preview frame generation;
- still capture;
- valid JPEG output;
- stop;
- repeated stop;
- invalid lifecycle operations if the contract defines them.

Run Pyright and pytest.
