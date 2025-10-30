#!/usr/bin/env python3
"""Build a standalone JennieBrowser bundle using PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = repo_root / "packaging" / "jenniebrowser.spec"

    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_path.relative_to(repo_root)),
        "--clean",
        "--noconfirm",
    ]

    subprocess.run(cmd, cwd=repo_root, check=True)


if __name__ == "__main__":
    main()
