# Toolchain

Do not add a frontend framework or streaming dependency.

Use:

- Flask;
- Jinja2 included with Flask;
- standard Python synchronization primitives;
- vanilla JavaScript;
- CSS.

# Documentation

Document:

- which component owns the camera instance;
- how preview frames are shared;
- behavior when a browser disconnects;
- behavior when the camera fails;
- shutdown behavior;
- expected limitations of MJPEG.

# Validation

Test HTTP behavior without a real camera using SyntheticCameraBackend.

Run Pyright and pytest.
