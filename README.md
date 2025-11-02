# JennieBrowser

JennieBrowser is a tiny PyQt-based web browser designed for everyday browsing
without extra bloat. It ships a classic single-window UI (back/forward/reload/
home, address bar) and bundles a lightweight rule-based ad blocker.

## Features

- Minimal chrome with the navigation controls you expect.
- Omnibox-style URL bar that falls back to DuckDuckGo search.
- Built-in ad blocking with a curated EasyList-inspired ruleset.
- Command-line options to customise homepage, startup URL, and filter lists.

## Quick Start

**Prerequisites**  
- Python 3.9 or newer.  
- A virtual environment is recommended to keep dependencies isolated.

**Install and run**

```bash
python -m venv .venv
source .venv/bin/activate

# Editable install keeps the package on your PYTHONPATH
pip install -e .

# Start the browser
jenniebrowser
# …or run it straight from the source tree
python -m jenniebrowser.app
```

> Prefer a lightweight setup? Replace the editable install with
> `pip install -r requirements.txt` and export `PYTHONPATH=src` before launching
> the module.

Run `python -m jenniebrowser.app --help` to see all supported flags.

### Command-Line Options

- `--homepage URL` – Override the homepage used by the Home button.
- `--filter-list PATH` – Load additional ad-block filters (flag accepts
  multiple occurrences). Files support a simplified EasyList syntax with
  `||domain.com`, `|http://prefix`, `*substring`, and `needle^` patterns.
- `--no-adblock` – Start with ad blocking disabled; the toolbar toggle remains
  available.
- `--version` – Print the current application version.

Passing a URL as the first positional argument opens that page immediately after
launch.

## Project Layout

- `src/jenniebrowser/app.py` – CLI entry point that parses args and boots Qt.
- `src/jenniebrowser/browser.py` – Main `QMainWindow` wiring widgets and web
  view behaviour.
- `src/jenniebrowser/adblocker.py` – Rule parsing and request filtering logic.
- `src/jenniebrowser/history.py` – In-memory navigation history model.
- `src/jenniebrowser/resources/` – Icons, HTML assets, and `default_filters.txt`
  (the bundled filter list).
- `build/`, `dist/` – Output directories created by packaging commands.
- `pyproject.toml`, `requirements.txt` – Project metadata and dependency pins.

Knowing where each piece lives makes it easier to tweak UI controls, extend the
ad blocker, or swap out resources.

## Development Workflow

1. Create or activate a virtual environment, then install dependencies with
   `pip install -e .`.
2. Launch `python -m jenniebrowser.app` for interactive debugging; Qt logs go to
   stdout.
3. Follow PEP 8, keep imports grouped (stdlib, third-party, local), and add type
   hints when extending APIs. The existing modules already import
   `from __future__ import annotations`.
4. No automated test suite exists yet. If you introduce one, prefer `pytest`
   under `tests/` and mirror module names (for example `tests/test_browser.py`).

## Ad Blocking Reference

- The bundled rules live in `src/jenniebrowser/resources/default_filters.txt`.
- Provide extra lists with `--filter-list path/to/list.txt`. Relative paths are
  resolved against the current working directory.
- Patterns follow a trimmed EasyList syntax:
  - `||domain.tld` blocks any request to that domain or subdomains.
  - `|http://example.com/ads` matches URL prefixes.
  - `*promo*` finds substrings anywhere in the URL.
  - `pixel^` blocks requests where `pixel` is followed by a separator (`?`, `/`,
    end of string, etc.).
- Toggle the ad blocker at runtime via the toolbar if a site misbehaves.

## Building & Distribution

JennieBrowser ships as a standard Python package, so you can rely on the core
packaging toolchain:

```bash
python -m build
```

Artifacts (`jenniebrowser-<version>.tar.gz` and `jenniebrowser-<version>-py3-none-any.whl`)
are written to `dist/`. Install them locally to verify a release:

```bash
pip install dist/jenniebrowser-<version>-py3-none-any.whl
# or isolate the install
pipx install dist/jenniebrowser-<version>-py3-none-any.whl
```

| Scenario | Command | Result |
| --- | --- | --- |
| Editable development install | `pip install -e .` | Live-editable package linked into your environment. |
| Wheel-based install | `pip install dist/jenniebrowser-<version>-py3-none-any.whl` | Standard pip installation from the wheel created by `python -m build`. |

## Manual Verification

Until automated tests land, run through these smoke checks after changes:

- Launch the app, ensure the default homepage loads, and basic navigation works.
- Visit a known ad-heavy page to confirm filters block obvious trackers.
- Toggle the ad blocker off/on via the toolbar to verify state changes.
- Supply a custom list (`--filter-list`) and confirm it loads without errors.
- Open a non-HTTP URL (e.g. `file://`) to make sure error handling is graceful.

Document any additional scenarios in pull requests to keep regression coverage
clear.

## License

This project is released under the MIT License. See `LICENSE`.
