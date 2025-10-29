"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QLineEdit, QMainWindow, QMessageBox, QSizePolicy, QStatusBar, QToolBar
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

from .adblocker import AdBlocker, RuleSet


class BrowserWindow(QMainWindow):
    """Single window browser with a minimal user interface."""

    def __init__(
        self,
        *,
        homepage: str,
        rule_paths: Iterable[Path],
        adblock_enabled: bool = True,
        window_icon: Optional[QIcon] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("JennieBrowser")
        if window_icon is not None:
            self.setWindowIcon(window_icon)

        self._homepage = homepage
        self._web_view = QWebEngineView(self)
        self._web_view.urlChanged.connect(self._update_url_bar)
        self._web_view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self._web_view)

        self._adblocker = self._install_adblocker(rule_paths, adblock_enabled)

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        self._address_bar = QLineEdit(self)
        self._address_bar.setClearButtonEnabled(True)
        self._address_bar.returnPressed.connect(self._on_url_entered)
        self._address_bar.setPlaceholderText("Enter URL or search term…")
        self._address_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._toolbar = self._build_toolbar()
        self.addToolBar(self._toolbar)

        self.load_homepage()

    # ------------------------------------------------------------------
    # Toolbar & actions
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)

        back_action = QAction("Back", self)
        back_action.triggered.connect(self._web_view.back)
        toolbar.addAction(back_action)

        forward_action = QAction("Forward", self)
        forward_action.triggered.connect(self._web_view.forward)
        toolbar.addAction(forward_action)

        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(self._web_view.reload)
        toolbar.addAction(reload_action)

        home_action = QAction("Home", self)
        home_action.triggered.connect(self.load_homepage)
        toolbar.addAction(home_action)

        toolbar.addWidget(self._address_bar)

        adblock_action = QAction("Ad Block", self)
        adblock_action.setCheckable(True)
        adblock_action.setChecked(self._adblocker.is_enabled())
        adblock_action.triggered.connect(self._toggle_adblock)
        toolbar.addAction(adblock_action)

        return toolbar

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_homepage(self) -> None:
        self._load_url(self._homepage)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_url_entered(self) -> None:
        text = self._address_bar.text().strip()
        if not text:
            return
        if self._looks_like_url(text):
            self._load_url(text)
        else:
            query = QUrl.toPercentEncoding(text)
            search_url = f"https://duckduckgo.com/?q={query.decode('utf-8')}"
            self._load_url(search_url)

    def _update_url_bar(self, url: QUrl) -> None:
        if url.toString() != self._address_bar.text():
            self._address_bar.setText(url.toString())

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            self._status_bar.showMessage("Loaded", 2000)
        else:
            self._status_bar.showMessage("Failed to load page", 4000)
            QMessageBox.warning(self, "Load Error", "The page could not be loaded.")

    def _toggle_adblock(self, checked: bool) -> None:
        self._adblocker.set_enabled(checked)
        state = "enabled" if checked else "disabled"
        self._status_bar.showMessage(f"Ad blocking {state}", 2000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_url(self, value: str) -> None:
        url = QUrl.fromUserInput(value)
        if not url.isValid():
            QMessageBox.warning(self, "Invalid URL", "The address you entered is not valid.")
            return
        self._web_view.setUrl(url)

    def _looks_like_url(self, text: str) -> bool:
        if " " in text:
            return False
        if text.startswith("http://") or text.startswith("https://"):
            return True
        return "." in text

    def _install_adblocker(self, rule_paths: Iterable[Path], enabled: bool) -> AdBlocker:
        rule_set = RuleSet.from_paths(rule_paths)
        adblocker = AdBlocker(rule_set, enabled=enabled)
        profile: QWebEngineProfile = QWebEngineProfile.defaultProfile()
        profile.setUrlRequestInterceptor(adblocker)
        return adblocker


__all__ = ["BrowserWindow"]
