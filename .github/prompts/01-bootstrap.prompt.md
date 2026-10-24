# Toolchain

Create the project with uv and add:

Runtime dependency:

- Flask.

Development dependencies:

- pytest;
- Pyright.

Do not add a linter or formatter.

Configure Pyright in strict mode, or as close to strict mode as is practical
without broad ignore rules.

Create fully typed and documented initial Python modules.

# Validation

Run:

- `uv run pyright`;
- `uv run pytest`.

Do not install dependencies globally.
