# Repository Guidelines

## Project Structure & Module Organization
Source code lives in `src/jenniebrowser/`, with `app.py` exposing the CLI entry point, `browser.py` wiring the main PyQt window, `adblocker.py` managing filter evaluation, and `history.py` storing in-memory navigation history. UI assets and the default filter bundle sit in `src/jenniebrowser/resources/`. Build outputs land in `build/` and `dist/`, while dependency metadata stays in `pyproject.toml` and `requirements.txt`. No dedicated `tests/` directory exists yet; place future suites under `tests/` at the repo root.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` – create and enter a local virtual environment.
- `pip install -e .` – install JennieBrowser in editable mode so imports resolve during development.
- `python -m jenniebrowser.app` – launch the browser directly from source; add `--help` to explore runtime flags.
- `jenniebrowser` – start the installed CLI entry point for manual smoke testing.
- `python -m build` – produce sdist and wheel artifacts in `dist/` for release validation.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation, `snake_case` modules and functions, and `CamelCase` Qt widgets. Type hints and `from __future__ import annotations` are standard across the codebase; continue using them when expanding APIs. Keep imports grouped (stdlib, third-party, local) and sorted, and prefer docstrings or concise comments for complex UI wiring.

## Testing Guidelines
Automated tests are not present yet. When adding them, prefer `pytest` under `tests/` and mirror module names (`test_browser.py`, etc.). Until then, cover key flows manually: startup, navigation, toggling the ad blocker, and loading custom filter lists. Document manual scenarios in PR descriptions, and consider temporary scripts under `tests/manual/` if they aid reproducibility.

## Commit & Pull Request Guidelines
Commits in history use short, imperative subjects (e.g., “Remove PyInstaller docs”). Keep messages under 72 characters and reference issues or PR numbers when relevant (`Refs #12`). Pull requests should describe changes, list manual verification steps, flag UI-visible updates with screenshots, and mention any new resources or packaging impacts.

## Configuration & Release Tips
Keep bundled filters lightweight: update `resources/default_filters.txt` sparingly and cite sources. When shipping a release, verify the icon and start page assets are present in `resources/` and test the wheel via `pip install dist/...whl` inside a clean environment. Use `--filter-list` paths relative to the project root when documenting examples.
