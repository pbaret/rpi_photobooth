---
description: Rules for Flask routes and application setup
applyTo: "src/photobooth/routes/**/*.py,src/photobooth/app.py"
---

# Flask rules

All Python code must be fully typed and documented according to the repository
instructions.

Routes are HTTP adapters.

They should:

1. validate HTTP input;
2. call application services;
3. translate application results or exceptions into HTTP responses.

Routes must not implement:

- camera behavior;
- subprocess management;
- filesystem storage logic;
- CUPS behavior.

Use Blueprints.

State-changing operations use POST.

Use Post/Redirect/Get where appropriate.

Never resolve a filesystem path supplied by a client.

Photos are addressed through validated opaque identifiers.

Handle relevant application conflicts explicitly, including duplicate
capture requests.

Do not return:

- filesystem paths;
- raw subprocess errors;
- administrator secrets;
- download tokens unrelated to the requesting operation.

Do not enable Flask debug mode when binding to a LAN-accessible interface.