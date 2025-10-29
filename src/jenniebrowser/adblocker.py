"""Utilities for lightweight ad blocking in the embedded web engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor


@dataclass
class RuleSet:
    """Container for ad blocking rules."""

    rules: List[str]

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> "RuleSet":
        """Create a :class:`RuleSet` by reading every provided path.

        Paths that do not exist are ignored to keep startup resilient. Empty
        and commented lines are skipped to keep the rule set small.
        """

        collected: List[str] = []
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith(("#", "!")):
                        continue
                    collected.append(line)
        return cls(collected)


class AdBlocker(QWebEngineUrlRequestInterceptor):
    """Very small ad blocker relying on a curated list of rules.

    The intent is not to be a fully featured uBlock replacement. The goal is to
    provide a simple filter that can block the most disruptive ad networks and
    trackers while keeping startup fast and dependencies minimal.
    """

    def __init__(self, rule_set: RuleSet | None = None, *, enabled: bool = True) -> None:
        super().__init__()
        self._rules: List[str] = rule_set.rules if rule_set else []
        self._enabled = enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:  # type: ignore[override]
        if not self._enabled or not self._rules:
            return

        url = info.requestUrl()
        if not url.isValid():
            return

        if self._should_skip(url):
            return

        media_types = {
            getattr(QWebEngineUrlRequestInfo.ResourceType, name)
            for name in (
                "ResourceTypeMedia",
                "ResourceTypeVideo",
                "ResourceTypePlugin",
                "ResourceTypePluginResource",
            )
            if hasattr(QWebEngineUrlRequestInfo.ResourceType, name)
        }
        if info.resourceType() in media_types:
            return

        if self._should_block(url):
            info.block(True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _should_skip(self, url: QUrl) -> bool:
        path = url.path()
        if "/cdn-cgi/speculation" in path:
            return True
        return False

    def _should_block(self, url: QUrl) -> bool:
        host = url.host().lower()
        url_str = url.toString().lower()
        for rule in self._rules:
            if self._matches_rule(rule, host, url_str):
                return True
        return False

    @staticmethod
    def _matches_rule(rule: str, host: str, url: str) -> bool:
        """Extremely small rule syntax compatible with a subset of EasyList."""

        if rule.startswith("||"):
            domain = rule[2:]
            return host.endswith(domain)
        if rule.startswith("|"):
            prefix = rule[1:]
            return url.startswith(prefix)
        if rule.startswith("*"):
            needle = rule[1:]
            return needle in url
        if rule.endswith("^"):
            needle = rule[:-1]
            return needle in url
        return rule in host or rule in url


__all__ = ["AdBlocker", "RuleSet"]
