# JennieBrowser

JennieBrowser is a tiny PyQt-based web browser aimed at daily browsing without
extra bloat. It exposes a classic single-window UI (back/forward/reload/home,
address bar) and bundles a lightweight rule-based ad blocker.

## Features

- Minimal UI with common navigation controls.
- URL bar doubles as a search box (DuckDuckGo by default).
- Built-in ad blocking powered by a curated EasyList-style filter list.
- Command-line options to customise homepage, startup URL, and filter lists.

## Getting Started

1. Install the project (this will also bring in the PyQt dependencies). A
   modern Python (3.9+) is required:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
    
   # Install JennieBrowser in editable mode so the package is on your PYTHONPATH
   pip install -e .
   ```

   > If you prefer not to install the package, replace the last command with
   > `pip install -r requirements.txt` and set `PYTHONPATH=src` before running
   > the application.

2. Launch the browser:

   ```bash
   # Installed entry point
   jenniebrowser

   # …or invoke the module directly
   python -m jenniebrowser.app
   ```

   Use `python -m jenniebrowser.app --help` to see all available options.

### Command-Line Options

- `--homepage URL` – Set the homepage used when hitting the Home button.
- `--filter-list PATH` – Supply extra ad-block filter files (can be used
  multiple times). Files use a simplified EasyList syntax with support for the
  `||domain.com`, `|http://prefix`, `*substring`, and `needle^` patterns.
- `--no-adblock` – Disable the ad blocker at launch. You can toggle it later
  from the toolbar.
- `--version` – Print the current application version.

If a start URL is passed as the first positional argument, JennieBrowser opens it
immediately after launching.

## Distribution

JennieBrowser ships as a standard Python package, so you can create release
artifacts with the core packaging toolchain:

```bash
python -m build
```

The command writes a source archive (`jenniebrowser-<version>.tar.gz`) and a
wheel (`jenniebrowser-<version>-py3-none-any.whl`) to `dist/`. Consumers can
install either artifact locally with pip:

```bash
pip install dist/jenniebrowser-<version>-py3-none-any.whl
# or, for an isolated application-style install
pipx install dist/jenniebrowser-<version>-py3-none-any.whl
```

### Installation cheat sheet

| Scenario | Command | Result |
| --- | --- | --- |
| Editable development install | `pip install -e .` | Live-editable package linked into your environment. |
| Wheel-based install | `pip install dist/jenniebrowser-<version>-py3-none-any.whl` | Standard pip installation from the wheel created by `python -m build`. |

## Development

- Format/linters are not enforced, but keeping imports sorted and code type
  hinted is appreciated.
- Tests are not included; manual testing is recommended after UI changes.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
