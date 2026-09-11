# Working in this repo

Prefer the `just` recipes in `justfile` over calling `uv run ...` directly. Run
`just --list` if unsure what's available. In particular:

- `just lint` — ruff check, ruff format --check, and mypy (not `uv run mypy` alone)
- `just fmt` — ruff format + ruff check --fix
- `just test [ARGS]` — pytest (not `uv run pytest` directly)
- `just test-all` — full tox matrix across supported Python/Django versions
- `just migrate` / `just makemigrations` — Django management commands for the webapp
- `just scan [path]` / `just submit [path] [url]` — run the CLI against a project

Only fall back to a raw `uv run` invocation when no recipe covers what's needed.

## Writing documentation

- Be concise and use simple language
- Avoid the tendency to write phrases such as "it does A and B, not X and Y"

## Writing tests

- Use concise names, extra context or description goes in the doc string
- Attempt to reuse/extend existing tests rather than adding new ones
