"""Lightweight persistent browsing history management."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .settings import CONFIG_DIR

HISTORY_PATH = CONFIG_DIR / "history.json"


@dataclass(slots=True)
class HistoryEntry:
    """Single browsing history record."""

    url: str
    title: str
    timestamp: str


class BrowserHistory:
    """Manage persistence of browsing history entries."""

    def __init__(
        self,
        entries: List[HistoryEntry] | None = None,
        *,
        path: Path = HISTORY_PATH,
        max_entries: int = 500,
    ) -> None:
        self._entries: List[HistoryEntry] = list(entries or [])
        self._path = path
        self._max_entries = max(1, max_entries)

    @classmethod
    def load(
        cls,
        *,
        path: Path | None = None,
        max_entries: int = 500,
    ) -> "BrowserHistory":
        path = path or HISTORY_PATH
        if not path.exists():
            return cls([], path=path, max_entries=max_entries)
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return cls([], path=path, max_entries=max_entries)

        entries: List[HistoryEntry] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                if not url:
                    continue
                title = str(item.get("title", "")).strip() or url
                timestamp = str(item.get("timestamp", "")).strip()
                if not timestamp:
                    timestamp = datetime.now().isoformat(timespec="seconds")
                entries.append(HistoryEntry(url=url, title=title, timestamp=timestamp))

        if len(entries) > max_entries:
            entries = entries[-max_entries:]

        return cls(entries, path=path, max_entries=max_entries)

    def save(self) -> None:
        data = [asdict(entry) for entry in self._entries[-self._max_entries :]]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def add_entry(self, url: str, title: str | None = None) -> None:
        url = (url or "").strip()
        if not url or url.startswith("about:") or url.startswith("data:"):
            return
        safe_title = (title or "").strip() or url
        entry = HistoryEntry(
            url=url,
            title=safe_title,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )
        if self._entries and self._entries[-1].url == entry.url:
            self._entries[-1] = entry
        else:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]
        self.save()

    def entries(self) -> Iterable[HistoryEntry]:
        """Return entries in reverse-chronological order."""

        return reversed(self._entries)

    def is_empty(self) -> bool:
        return not self._entries


__all__ = ["BrowserHistory", "HistoryEntry", "HISTORY_PATH"]
