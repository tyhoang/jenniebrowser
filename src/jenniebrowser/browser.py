"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QUrl
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
    QTabWidget,
    QVBoxLayout,
)
from PyQt6.QtWebEngineCore import QWebEngineFullScreenRequest, QWebEngineProfile, QWebEngineSettings
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
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.tabCloseRequested.connect(self._close_tab)
        self._tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self._tab_widget)

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

        self._apply_privacy_defaults()
        self._shortcuts = []
        self._install_shortcuts()
        self._apply_settings()
        self._add_tab(self._homepage)
        self._on_current_tab_changed(self._tab_widget.currentIndex())

    # ------------------------------------------------------------------
    # Toolbar & actions
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)

        back_action = QAction("Back", self)
        back_action.triggered.connect(self._navigate_back)
        toolbar.addAction(back_action)

        forward_action = QAction("Forward", self)
        forward_action.triggered.connect(self._navigate_forward)
        toolbar.addAction(forward_action)

        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(self._reload_current)
        toolbar.addAction(reload_action)

        home_action = QAction("Home", self)
        home_action.triggered.connect(self.load_homepage)
        toolbar.addAction(home_action)

        new_tab_action = QAction("New Tab", self)
        new_tab_action.triggered.connect(self._open_new_tab)
        toolbar.addAction(new_tab_action)

        toolbar.addWidget(self._address_bar)

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

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._settings = dialog.apply()
            self._apply_settings()
            self._status_bar.showMessage("Settings updated", 2000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_url(self, value: str) -> None:
        url = QUrl.fromUserInput(value)
        if not url.isValid():
            QMessageBox.warning(self, "Invalid URL", "The address you entered is not valid.")
            return
        view = self._current_web_view()
        if view is None:
            view = self._add_tab(url.toString())
        else:
            view.setUrl(url)

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
            (QKeySequence("Shift+H"), self._navigate_back),
            (QKeySequence("Shift+L"), self._navigate_forward),
            (QKeySequence("R"), self._reload_current),
            (QKeySequence("O"), self._focus_address_bar),
            (QKeySequence("J"), self._scroll_down),
            (QKeySequence("K"), self._scroll_up),
            (QKeySequence("Escape"), self._maybe_unfocus_address_bar),
            (QKeySequence("Shift+T"), self._open_new_tab),
            (QKeySequence("Shift+W"), self._close_current_tab),
        ]
        for sequence, handler in mappings:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)  # type: ignore[arg-type]
            self._shortcuts.append(shortcut)

    def _focus_address_bar(self) -> None:
        self._address_bar.setFocus()
        self._address_bar.selectAll()

    def _maybe_unfocus_address_bar(self) -> None:
        if self._address_bar.hasFocus():
            self._address_bar.deselect()
            self._address_bar.clearFocus()
            view = self._current_web_view()
            if view is not None:
                view.setFocus()

    def _scroll_down(self) -> None:
        view = self._current_web_view()
        if view is None:
            return
        view.page().runJavaScript("window.scrollBy({top: 120, left: 0, behavior: 'smooth'});")

    def _scroll_up(self) -> None:
        view = self._current_web_view()
        if view is None:
            return
        view.page().runJavaScript("window.scrollBy({top: -120, left: 0, behavior: 'smooth'});")

    def _apply_privacy_defaults(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
        profile.setHttpUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def _configure_web_view(self, view: QWebEngineView) -> None:
        page = view.page()
        page.setAudioMuted(False)
        page.fullScreenRequested.connect(self._accept_fullscreen_request)
        settings = view.settings()
        attribute_map = {
            "FullScreenSupportEnabled": True,
            "PluginsEnabled": True,
            "JavascriptEnabled": True,
            "PlaybackRequiresUserGesture": False,
            "WebGLEnabled": True,
            "Accelerated2dCanvasEnabled": True,
            "WebAudioEnabled": True,
        }
        for name, value in attribute_map.items():
            attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
            if attribute is not None:
                settings.setAttribute(attribute, value)
        view.setZoomFactor(self._settings.zoom_factor)

    def _accept_fullscreen_request(self, request: QWebEngineFullScreenRequest) -> None:
        request.accept()

    def _apply_settings(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        color_scheme_enum = getattr(QWebEngineProfile, "ColorScheme", None)
        if color_scheme_enum is not None:
            dark_value = getattr(color_scheme_enum, "Dark", getattr(color_scheme_enum, "ColorSchemeDark", None))
            light_value = getattr(color_scheme_enum, "Light", getattr(color_scheme_enum, "ColorSchemeLight", None))
            if dark_value is not None and light_value is not None:
                profile.setColorScheme(dark_value if self._settings.dark_mode else light_value)
        for view in self._iter_web_views():
            view.setZoomFactor(self._settings.zoom_factor)
        self._adblocker.set_enabled(self._settings.adblock_enabled)

    def _iter_web_views(self) -> Iterable[QWebEngineView]:
        for index in range(self._tab_widget.count()):
            widget = self._tab_widget.widget(index)
            if isinstance(widget, QWebEngineView):
                yield widget

    def _current_web_view(self) -> Optional[QWebEngineView]:
        widget = self._tab_widget.currentWidget()
        if isinstance(widget, QWebEngineView):
            return widget
        return None

    def _create_web_view(self) -> QWebEngineView:
        view = QWebEngineView(self)
        self._configure_web_view(view)
        view.urlChanged.connect(lambda url, view=view: self._on_url_changed(view, url))
        view.loadFinished.connect(lambda ok, view=view: self._on_load_finished(view, ok))
        view.titleChanged.connect(lambda title, view=view: self._update_tab_title(view, title))
        view.iconChanged.connect(lambda icon, view=view: self._update_tab_icon(view, icon))
        return view

    def _add_tab(self, url: str | None = None, *, focus: bool = True) -> QWebEngineView:
        view = self._create_web_view()
        index = self._tab_widget.addTab(view, "New Tab")
        if focus:
            self._tab_widget.setCurrentIndex(index)
        if url:
            target = QUrl.fromUserInput(url)
        else:
            target = QUrl("about:blank")
        view.setUrl(target)
        return view

    def _open_new_tab(self) -> None:
        self._add_tab(self._homepage)
        self._focus_address_bar()

    def _close_current_tab(self) -> None:
        index = self._tab_widget.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _close_tab(self, index: int) -> None:
        if self._tab_widget.count() == 1:
            view = self._tab_widget.widget(index)
            if isinstance(view, QWebEngineView):
                view.setUrl(QUrl("about:blank"))
                self._tab_widget.setTabText(index, "New Tab")
                self._tab_widget.setTabIcon(index, QIcon())
            self._address_bar.clear()
            return
        widget = self._tab_widget.widget(index)
        self._tab_widget.removeTab(index)
        if widget is not None:
            widget.deleteLater()

    def _on_current_tab_changed(self, index: int) -> None:
        view = self._current_web_view()
        if view is None:
            self._address_bar.clear()
            return
        self._address_bar.setText(view.url().toString())
        view.setFocus()

    def _on_url_changed(self, view: QWebEngineView, url: QUrl) -> None:
        if view is self._current_web_view():
            if url.toString() != self._address_bar.text():
                self._address_bar.setText(url.toString())

    def _on_load_finished(self, view: QWebEngineView, ok: bool) -> None:
        if view is self._current_web_view():
            if ok:
                self._status_bar.showMessage("Loaded", 2000)
            else:
                self._status_bar.showMessage("Failed to load page", 4000)
                QMessageBox.warning(self, "Load Error", "The page could not be loaded.")
        if ok:
            self._update_tab_title(view, view.title() or "New Tab")

    def _update_tab_title(self, view: QWebEngineView, title: str) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabText(index, title or "New Tab")

    def _update_tab_icon(self, view: QWebEngineView, icon: QIcon) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabIcon(index, icon)

    def _navigate_back(self) -> None:
        view = self._current_web_view()
        if view is not None:
            view.back()

    def _navigate_forward(self) -> None:
        view = self._current_web_view()
        if view is not None:
            view.forward()

    def _reload_current(self) -> None:
        view = self._current_web_view()
        if view is not None:
            view.reload()


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
