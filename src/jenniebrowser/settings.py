"""Persistent configuration management for JennieBrowser."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

CONFIG_DIR = Path.home() / ".config" / "jenniebrowser"
CONFIG_PATH = CONFIG_DIR / "settings.json"


def _coerce_zoom(value: Any, default: float) -> float:
    try:
        zoom = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.25, min(zoom, 5.0))


def _coerce_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _coerce_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
    return items


@dataclass
class BrowserSettings:  # pylint: disable=too-many-instance-attributes
    """Simple settings container stored on disk as JSON."""

    dark_mode: bool = True
    zoom_factor: float = 1.0
    adblock_enabled: bool = True
    block_popups: bool = True
    restore_session: bool = True
    last_session: List[str] = field(default_factory=list, repr=False)
    last_session_index: int = 0
    _path: Path = field(default=CONFIG_PATH, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "BrowserSettings":
        """Read settings from ``path`` or create defaults when missing."""
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
            block_popups=bool(raw.get("block_popups", True)),
            restore_session=bool(raw.get("restore_session", True)),
            last_session=_coerce_list(raw.get("last_session", [])),
            last_session_index=_coerce_int(raw.get("last_session_index", 0), 0),
            _path=path,
        )
        return settings

    def save(self, path: Path | None = None) -> None:
        """Persist the current configuration to disk."""
        path = path or self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_path", None)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    # pylint: disable=too-many-arguments
    def update(
        self,
        *,
        dark_mode: bool | None = None,
        zoom_factor: float | None = None,
        adblock_enabled: bool | None = None,
        block_popups: bool | None = None,
        restore_session: bool | None = None,
    ) -> None:
        """Apply in-memory changes and persist them."""
        if dark_mode is not None:
            self.dark_mode = bool(dark_mode)
        if zoom_factor is not None:
            self.zoom_factor = _coerce_zoom(zoom_factor, self.zoom_factor)
        if adblock_enabled is not None:
            self.adblock_enabled = bool(adblock_enabled)
        if block_popups is not None:
            self.block_popups = bool(block_popups)
        if restore_session is not None:
            self.restore_session = bool(restore_session)
        self.save()

    def store_session(self, urls: List[str], current_index: int) -> None:
        """Persist the most recent session details for restoration."""
        self.last_session = urls
        self.last_session_index = min(max(current_index, 0), max(len(urls) - 1, 0))
        self.save()


__all__ = ["BrowserSettings", "CONFIG_PATH"]
