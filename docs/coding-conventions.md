# Coding Conventions

## Language

- Keep code comments in English.
- Keep docstrings in English.
- Keep CLI help text in English.
- Keep exception and log messages in English.
- User-facing planning notes can stay in Turkish while the project is under active development.

## Python Package Structure

- Use `__init__.py` to make package boundaries explicit.
- Re-export only the public API that other modules are expected to import.
- Keep module responsibilities narrow: models, ingestion, services, and state should stay separate.

## Project Goal

- Optimize for a clean, GitHub-shareable codebase.
- Prefer explicit, readable structure over clever shortcuts.
