# Toolchain

Add OpenCV as a runtime dependency required by the PC camera backend.

Use the headless package only if the application does not require OpenCV GUI
windows. The browser, not OpenCV, provides the user interface.

# Documentation

Document:

- VideoCapture ownership;
- start and stop idempotency;
- locking model;
- preview mirroring;
- capture mirroring behavior;
- requested versus effective resolution;
- unavailable or busy webcam errors.

# Validation

Automated tests must mock the OpenCV boundary and work without a webcam.

Also provide a separate manual diagnostic command for webcam index 0.

Run Pyright and pytest.
