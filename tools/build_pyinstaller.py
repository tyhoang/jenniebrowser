"""Helper script to produce a PyInstaller binary for JennieBrowser."""

from __future__ import annotations

from pathlib import Path

from PyInstaller.__main__ import run as pyinstaller_run


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = repo_root / "packaging" / "jenniebrowser.spec"
    work_path = repo_root / "build" / "pyinstaller"
    dist_path = repo_root / "dist" / "pyinstaller"

    work_path.mkdir(parents=True, exist_ok=True)
    dist_path.mkdir(parents=True, exist_ok=True)

    args = [
        str(spec_path),
        "--noconfirm",
        "--clean",
        f"--workpath={work_path}",
        f"--distpath={dist_path}",
    ]

    pyinstaller_run(args)


if __name__ == "__main__":  # pragma: no cover - tooling script
    main()
