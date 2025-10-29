"""Entry point for launching JennieBrowser from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import __version__
from .browser import BrowserWindow


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the lightweight JennieBrowser web browser")
    parser.add_argument("start", nargs="?", default=None, help="Optional URL to load on startup")
    parser.add_argument("--homepage", default="https://duckduckgo.com", help="Homepage used by the Home button")
    parser.add_argument(
        "--filter-list",
        action="append",
        dest="filters",
        default=None,
        help="Path to an additional ad-block filter list (can be provided multiple times)",
    )
    parser.add_argument("--no-adblock", action="store_true", help="Start without the ad blocker enabled")
    parser.add_argument("--version", action="store_true", help="Show the version and exit")
    return parser


def _collect_filter_paths(extra: Iterable[str] | None) -> List[Path]:
    base = Path(__file__).resolve().parent
    default_filter = base / "resources" / "default_filters.txt"
    paths = [default_filter]
    if extra:
        paths.extend(Path(item).expanduser() for item in extra)
    return paths


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    if args.version:
        print(f"JennieBrowser {__version__}")
        return 0

    app = QApplication(argv)
    icon_path = Path(__file__).resolve().parent / "resources" / "icon.png"
    window_icon = QIcon(str(icon_path)) if icon_path.exists() else None

    start_url = args.start
    homepage = args.homepage
    filters = _collect_filter_paths(args.filters)

    window = BrowserWindow(
        start_url=start_url,
        homepage=homepage,
        rule_paths=filters,
        adblock_enabled=not args.no_adblock,
        window_icon=window_icon,
        start_url=start_url,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual entry point
    sys.exit(main())
