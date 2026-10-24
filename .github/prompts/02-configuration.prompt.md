# Toolchain

Do not add a dependency unless the standard library cannot meet the accepted
configuration design.

Prefer:

- dataclasses;
- enums;
- pathlib;
- json;
- os.environ;
- typing.

Do not introduce Pydantic unless its concrete benefit is documented and
approved before implementation.

# Documentation

Document:

- precedence between defaults, JSON file and environment variables;
- static startup settings versus runtime-editable settings;
- atomic write behavior;
- validation failures;
- restart-required settings.

# Validation

Add pytest tests for:

- defaults;
- environment overrides;
- valid JSON;
- malformed JSON;
- numeric bounds;
- atomic persistence;
- absence of configuration files.

Run Pyright and pytest.
