"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
)
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

from .adblocker import AdBlocker, RuleSet
from .settings import BrowserSettings


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
        self._settings = BrowserSettings.load()
        self._web_view = QWebEngineView(self)
        self._web_view.urlChanged.connect(self._update_url_bar)
        self._web_view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self._web_view)

        self._adblocker = self._install_adblocker(rule_paths, self._settings.adblock_enabled and adblock_enabled)

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        self._address_bar = QLineEdit(self)
        self._address_bar.setClearButtonEnabled(True)
        self._address_bar.returnPressed.connect(self._on_url_entered)
        self._address_bar.setPlaceholderText("Enter URL or search term…")
        self._address_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._toolbar = self._build_toolbar()
        self.addToolBar(self._toolbar)

        self._shortcuts = []
        self._install_shortcuts()

        self._apply_privacy_defaults()
        self._apply_settings()

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

        self._adblock_action = QAction("Ad Block", self)
        self._adblock_action.setCheckable(True)
        self._adblock_action.setChecked(self._adblocker.is_enabled())
        self._adblock_action.triggered.connect(self._toggle_adblock)
        toolbar.addAction(self._adblock_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        toolbar.addAction(settings_action)

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
        self._settings.update(adblock_enabled=checked)

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._settings = dialog.apply()
            self._apply_settings()
            self._adblock_action.setChecked(self._settings.adblock_enabled)
            self._status_bar.showMessage("Settings updated", 2000)

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

    def _install_shortcuts(self) -> None:
        mappings = [
            (QKeySequence("Shift+H"), self._web_view.back),
            (QKeySequence("Shift+L"), self._web_view.forward),
            (QKeySequence("R"), self._web_view.reload),
            (QKeySequence("O"), self._focus_address_bar),
        ]
        for sequence, handler in mappings:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)  # type: ignore[arg-type]
            self._shortcuts.append(shortcut)

    def _focus_address_bar(self) -> None:
        self._address_bar.setFocus()
        self._address_bar.selectAll()

    def _apply_privacy_defaults(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setHttpCacheMaximumSize(0)

    def _apply_settings(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        color_scheme_enum = getattr(QWebEngineProfile, "ColorScheme", None)
        if color_scheme_enum is not None:
            dark_value = getattr(color_scheme_enum, "Dark", getattr(color_scheme_enum, "ColorSchemeDark", None))
            light_value = getattr(color_scheme_enum, "Light", getattr(color_scheme_enum, "ColorSchemeLight", None))
            if dark_value is not None and light_value is not None:
                profile.setColorScheme(dark_value if self._settings.dark_mode else light_value)
        self._web_view.setZoomFactor(self._settings.zoom_factor)
        self._adblocker.set_enabled(self._settings.adblock_enabled)


class SettingsDialog(QDialog):
    """Modal dialog for adjusting browser settings."""

    def __init__(self, settings: BrowserSettings, parent: Optional[QMainWindow] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Browser Settings")
        self._settings = settings

        self._dark_mode_checkbox = QCheckBox("Enable dark mode", self)
        self._dark_mode_checkbox.setChecked(settings.dark_mode)

        self._zoom_spinbox = QDoubleSpinBox(self)
        self._zoom_spinbox.setMinimum(0.25)
        self._zoom_spinbox.setMaximum(5.0)
        self._zoom_spinbox.setSingleStep(0.1)
        self._zoom_spinbox.setValue(settings.zoom_factor)

        self._adblock_checkbox = QCheckBox("Enable ad and tracker blocking", self)
        self._adblock_checkbox.setChecked(settings.adblock_enabled)

        form_layout = QFormLayout()
        form_layout.addRow(self._dark_mode_checkbox)
        form_layout.addRow("Zoom", self._zoom_spinbox)
        form_layout.addRow(self._adblock_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def apply(self) -> BrowserSettings:
        self._settings.update(
            dark_mode=self._dark_mode_checkbox.isChecked(),
            zoom_factor=self._zoom_spinbox.value(),
            adblock_enabled=self._adblock_checkbox.isChecked(),
        )
        return self._settings


__all__ = ["BrowserWindow"]
