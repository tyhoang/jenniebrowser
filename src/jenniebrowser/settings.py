"""Persistent configuration management for JennieBrowser."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "jenniebrowser"
CONFIG_PATH = CONFIG_DIR / "settings.json"


def _coerce_zoom(value: Any, default: float) -> float:
    try:
        zoom = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.25, min(zoom, 5.0))


@dataclass
class BrowserSettings:
    """Simple settings container stored on disk as JSON."""

    dark_mode: bool = True
    zoom_factor: float = 1.0
    adblock_enabled: bool = True
    _path: Path = field(default=CONFIG_PATH, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "BrowserSettings":
        path = path or CONFIG_PATH
        if not path.exists():
            settings = cls(_path=path)
            settings.save(path)
            return settings

        with path.open("r", encoding="utf-8") as handle:
            raw: Dict[str, Any] = json.load(handle)

        settings = cls(
            dark_mode=bool(raw.get("dark_mode", True)),
            zoom_factor=_coerce_zoom(raw.get("zoom_factor", 1.0), 1.0),
            adblock_enabled=bool(raw.get("adblock_enabled", True)),
            _path=path,
        )
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_path", None)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def update(
        self,
        *,
        dark_mode: bool | None = None,
        zoom_factor: float | None = None,
        adblock_enabled: bool | None = None,
    ) -> None:
        if dark_mode is not None:
            self.dark_mode = bool(dark_mode)
        if zoom_factor is not None:
            self.zoom_factor = _coerce_zoom(zoom_factor, self.zoom_factor)
        if adblock_enabled is not None:
            self.adblock_enabled = bool(adblock_enabled)
        self.save()


__all__ = ["BrowserSettings", "CONFIG_PATH"]
