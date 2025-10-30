"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable, Optional, cast

from PyQt6.QtCore import QUrl, Qt, QByteArray, QEvent, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStatusBar,
    QStyle,
    QToolBar,
    QTabWidget,
    QToolButton,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtWebEngineCore import (
    QWebEngineFullScreenRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from .adblocker import AdBlocker, RuleSet
from .history import BrowserHistory
from .settings import BrowserSettings, CONFIG_DIR


_START_PAGE_PATH = Path(__file__).resolve().parent / "resources" / "startpage.html"
if _START_PAGE_PATH.exists():
    _START_PAGE_URL = QUrl.fromLocalFile(str(_START_PAGE_PATH))
else:
    _START_PAGE_URL = QUrl("about:blank")


_LOG_PATH = CONFIG_DIR / "jenniebrowser.log"


def _ensure_logging_configured() -> logging.Logger:
    """Configure a rotating log file for runtime diagnostics."""

    logger = logging.getLogger("jenniebrowser.browser")
    if getattr(_ensure_logging_configured, "_configured", False):
        return logger

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        _LOG_PATH,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    setattr(_ensure_logging_configured, "_configured", True)
    logger.info("Logging initialised at %s", _LOG_PATH)
    return logger


LOGGER = _ensure_logging_configured()


class BrowserWebView(QWebEngineView):
    """Custom ``QWebEngineView`` that integrates with the tabbed UI."""

    def __init__(self, browser_window: "BrowserWindow") -> None:
        super().__init__(browser_window)
        self._browser_window = browser_window

    # Qt calls this when a page requests a new window (e.g. "open link in new tab").
    def createWindow(
        self, window_type: QWebEnginePage.WebWindowType
    ) -> QWebEngineView | None:  # type: ignore[override]
        LOGGER.info("createWindow requested with type %s", window_type)
        return self._browser_window._handle_new_window_request(window_type)
class BrowserWindow(QMainWindow):
    """Single window browser with a minimal user interface."""

    def __init__(
        self,
        *,
        start_url: QUrl | str | None = None,
        homepage: str,
        rule_paths: Iterable[Path],
        adblock_enabled: bool = True,
        window_icon: Optional[QIcon] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("JennieBrowser")
        if window_icon is not None:
            self.setWindowIcon(window_icon)

        self._start_page_url = _START_PAGE_URL
        self._homepage = homepage
        self._settings = BrowserSettings.load()
        self._history = BrowserHistory.load()
        resources_dir = Path(__file__).resolve().parent / "resources"
        start_page_path = resources_dir / "startpage.html"
        if start_page_path.exists():
            self._start_page_url = QUrl.fromLocalFile(str(start_page_path))
        else:
            self._start_page_url = QUrl("about:blank")
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.tabCloseRequested.connect(self._close_tab)
        self._tab_widget.currentChanged.connect(self._on_current_tab_changed)
        tab_bar = self._tab_widget.tabBar()
        tab_bar.setExpanding(True)
        tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        tab_bar.installEventFilter(self)
        self.setCentralWidget(self._tab_widget)

        self._new_tab_action = QAction("New Tab", self)
        self._new_tab_action.triggered.connect(self._open_new_tab)

        self._new_tab_button = QToolButton(self)
        self._new_tab_button.setDefaultAction(self._new_tab_action)
        self._new_tab_button.setAutoRaise(True)
        self._new_tab_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._new_tab_button.setText("+")
        self._new_tab_button.setToolTip("Open a new tab (Ctrl+T)")
        self._tab_widget.setCornerWidget(self._new_tab_button, Qt.Corner.TopRightCorner)

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
        self._is_fullscreen = False
        self._stored_geometry: QByteArray | None = None
        self._install_shortcuts()
        self._block_popups = self._settings.block_popups
        self._apply_settings()
        self._add_tab(self._start_page_url)
        if start_url:
            self._add_tab(start_url)
        self._on_current_tab_changed(self._tab_widget.currentIndex())

    # ------------------------------------------------------------------
    # Toolbar & actions
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        style = self.style()

        style = self.style()

        back_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Back", self)
        back_action.triggered.connect(self._navigate_back)
        back_action.setToolTip("Back (Shift+H)")
        toolbar.addAction(back_action)

        forward_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "Forward", self
        )
        forward_action.triggered.connect(self._navigate_forward)
        forward_action.setToolTip("Forward (Shift+L)")
        toolbar.addAction(forward_action)

        reload_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Reload", self
        )
        reload_action.triggered.connect(self._reload_current)
        reload_action.setToolTip("Reload (R)")
        toolbar.addAction(reload_action)

        home_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "Home", self)
        home_action.triggered.connect(self.load_homepage)
        home_action.setToolTip("Home")
        toolbar.addAction(home_action)

        toolbar.addWidget(self._address_bar)

        history_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "History", self
        )
        history_action.triggered.connect(self._open_history_dialog)
        toolbar.addAction(history_action)

        settings_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView), "Settings", self
        )
        settings_action.triggered.connect(self._open_settings_dialog)
        settings_action.setToolTip("Settings")
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
        dialog.clearDataRequested.connect(self._clear_site_data)
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

    def _handle_new_window_request(
        self, window_type: QWebEnginePage.WebWindowType
    ) -> QWebEngineView | None:
        tab_types = {
            QWebEnginePage.WebWindowType.WebBrowserTab,
            QWebEnginePage.WebWindowType.WebBrowserBackgroundTab,
        }

        if self._block_popups and window_type not in tab_types:
            LOGGER.info("Blocked new window request of type %s", window_type)
            self._status_bar.showMessage("Blocked a pop-up", 3000)
            return None

        focus = window_type != QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        LOGGER.info("Allowing new window request of type %s", window_type)
        return self._add_tab(
            None,
            focus=focus,
            load_default_url=False,
        )

    def _install_shortcuts(self) -> None:
        mappings = [
            (QKeySequence("Shift+H"), self._navigate_back),
            (QKeySequence("Shift+L"), self._navigate_forward),
            (QKeySequence("R"), self._reload_current),
            (QKeySequence("O"), self._focus_address_bar),
            (QKeySequence("Ctrl+L"), self._focus_address_bar),
            (QKeySequence("J"), self._scroll_down),
            (QKeySequence("K"), self._scroll_up),
            (QKeySequence("Escape"), self._clear_text_focus),
            (QKeySequence("Shift+T"), self._open_new_tab),
            (QKeySequence("Shift+W"), self._close_current_tab),
            (QKeySequence("Ctrl+T"), self._open_new_tab),
            (QKeySequence("Ctrl+W"), self._close_current_tab),
        ]
        for sequence, handler in mappings:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)  # type: ignore[arg-type]
            self._shortcuts.append(shortcut)

    def _focus_address_bar(self) -> None:
        self._address_bar.setFocus()
        self._address_bar.selectAll()

    def _clear_text_focus(self) -> None:
        view = self._current_web_view()
        address_bar_had_focus = self._address_bar.hasFocus()
        if address_bar_had_focus:
            self._address_bar.deselect()
            self._address_bar.clearFocus()

        if view is not None:
            script = """
                (function() {
                    let cleared = false;
                    const active = document.activeElement;
                    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) {
                        active.blur();
                        cleared = true;
                    }
                    const selection = window.getSelection();
                    if (selection && selection.rangeCount > 0) {
                        selection.removeAllRanges();
                        cleared = true;
                    }
                    return cleared;
                })();
            """
            view.page().runJavaScript(script)
            view.setFocus()
        elif address_bar_had_focus:
            self.setFocus()

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
        storage_root = CONFIG_DIR / "profile"
        storage_dir = storage_root / "storage"
        cache_dir = storage_root / "cache"
        cookies_dir = storage_root / "cookies"
        for path in (storage_dir, cache_dir, cookies_dir):
            path.mkdir(parents=True, exist_ok=True)

        profile.setPersistentStoragePath(str(storage_dir))
        profile.setCachePath(str(cache_dir))
        if hasattr(profile, "setPersistentCookieStorePath"):
            profile.setPersistentCookieStorePath(str(cookies_dir))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setHttpCacheMaximumSize(256 * 1024 * 1024)
        default_user_agent = profile.httpUserAgent()
        profile.setHttpUserAgent(default_user_agent)

    def _clear_site_data(self) -> None:
        profile = QWebEngineProfile.defaultProfile()
        storage_root = CONFIG_DIR / "profile"
        cookie_store = profile.cookieStore()
        cookie_store.deleteAllCookies()
        profile.clearHttpCache()
        clear_visited = getattr(profile, "clearAllVisitedLinks", None)
        if callable(clear_visited):
            clear_visited()

        if storage_root.exists():
            shutil.rmtree(storage_root, ignore_errors=True)

        self._apply_privacy_defaults()
        for view in self._iter_web_views():
            view.reload()
        self._status_bar.showMessage("Site data cleared", 2000)

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
        if request.toggleOn():
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _enter_fullscreen(self) -> None:
        if self._is_fullscreen:
            return
        self._stored_geometry = self.saveGeometry()
        self._toolbar.setVisible(False)
        self._status_bar.setVisible(False)
        self._tab_widget.tabBar().setVisible(False)
        self.showFullScreen()
        self._is_fullscreen = True

    def _exit_fullscreen(self) -> None:
        if not self._is_fullscreen:
            return
        self.showNormal()
        if self._stored_geometry is not None:
            self.restoreGeometry(self._stored_geometry)
        self._toolbar.setVisible(True)
        self._status_bar.setVisible(True)
        self._tab_widget.tabBar().setVisible(True)
        self._is_fullscreen = False

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
        self._block_popups = self._settings.block_popups

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
        view = BrowserWebView(self)
        self._configure_web_view(view)
        LOGGER.info("Created web view")
        view.urlChanged.connect(lambda url, view=view: self._on_url_changed(view, url))
        view.loadFinished.connect(lambda ok, view=view: self._on_load_finished(view, ok))
        view.titleChanged.connect(lambda title, view=view: self._update_tab_title(view, title))
        view.iconChanged.connect(lambda icon, view=view: self._update_tab_icon(view, icon))
        return view

    def _add_tab(
        self,
        url: str | QUrl | None = None,
        *,
        focus: bool = True,
        load_default_url: bool = True,
    ) -> QWebEngineView:
        view = self._create_web_view()
        index = self._tab_widget.addTab(view, "New Tab")
        if focus:
            self._tab_widget.setCurrentIndex(index)
        target: Optional[QUrl]
        if isinstance(url, QUrl):
            target = url
        elif isinstance(url, str):
            target = QUrl.fromUserInput(url)
        elif load_default_url:
            target = self._start_page_url
        else:
            target = None
        if target is not None:
            if not target.isValid():
                target = QUrl("about:blank")
            LOGGER.info("Opening URL %s in new tab", target.toString())
            view.setUrl(target)
        return view

    def _open_new_tab(self) -> None:
        self._add_tab(None)
        self._focus_address_bar()

    def _close_current_tab(self) -> None:
        index = self._tab_widget.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _close_tab(self, index: int) -> None:
        if self._tab_widget.count() == 1:
            view = self._tab_widget.widget(index)
            if isinstance(view, QWebEngineView):
                view.setUrl(self._start_page_url if self._start_page_url.isValid() else QUrl("about:blank"))
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
        if not ok:
            LOGGER.warning(
                "Load failure for %s",
                view.url().toString(),
            )
        else:
            LOGGER.info(
                "Load finished for %s",
                view.url().toString(),
            )
        if view is self._current_web_view():
            if ok:
                self._status_bar.showMessage("Loaded", 2000)
            else:
                self._status_bar.showMessage("Failed to load page", 4000)
                QMessageBox.warning(self, "Load Error", "The page could not be loaded.")
        if ok:
            self._update_tab_title(view, view.title() or "New Tab")
            self._history.add_entry(view.url().toString(), view.title())

    def _update_tab_title(self, view: QWebEngineView, title: str) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabText(index, title or "New Tab")

    def _update_tab_icon(self, view: QWebEngineView, icon: QIcon) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabIcon(index, icon)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._tab_widget.tabBar() and event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = cast(QMouseEvent, event)
            if mouse_event.button() == Qt.MouseButton.MiddleButton:
                tab_index = self._tab_widget.tabBar().tabAt(mouse_event.position().toPoint())
                if tab_index != -1:
                    self._close_tab(tab_index)
                    return True
        return super().eventFilter(obj, event)

    def _open_history_dialog(self) -> None:
        dialog = HistoryDialog(self._history, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.selected_url()
            if url:
                self._load_url(url)

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


class HistoryDialog(QDialog):
    """Simple dialog to inspect and open browsing history entries."""

    def __init__(self, history: BrowserHistory, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Browsing History")
        self.resize(500, 420)

        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._list)

        for entry in history.entries():
            try:
                when = datetime.fromisoformat(entry.timestamp).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                when = entry.timestamp
            text = f"{entry.title}\n{entry.url}\n{when}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.url)
            item.setToolTip(entry.url)
            self._list.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._open_button = buttons.addButton("Open", QDialogButtonBox.ButtonRole.AcceptRole)
        self._open_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._list.currentItemChanged.connect(self._on_current_item_changed)
        self._list.itemDoubleClicked.connect(lambda _: self.accept())
        self._list.itemActivated.connect(lambda _: self.accept())

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,  # noqa: ARG002
    ) -> None:
        self._open_button.setEnabled(current is not None)

    def selected_url(self) -> str:
        item = self._list.currentItem()
        if item is None:
            return ""
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data is not None else ""

    def accept(self) -> None:  # type: ignore[override]
        if self.selected_url():
            super().accept()


class SettingsDialog(QDialog):
    """Modal dialog for adjusting browser settings."""

    clearDataRequested = pyqtSignal()

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

        self._block_popups_checkbox = QCheckBox("Block pop-ups and site-opened tabs", self)
        self._block_popups_checkbox.setChecked(settings.block_popups)

        form_layout = QFormLayout()
        form_layout.addRow(self._dark_mode_checkbox)
        form_layout.addRow("Zoom", self._zoom_spinbox)
        form_layout.addRow(self._adblock_checkbox)
        form_layout.addRow(self._block_popups_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        clear_button = QPushButton("Clear site data", self)
        buttons.addButton(clear_button, QDialogButtonBox.ButtonRole.ActionRole)
        clear_button.clicked.connect(self._on_clear_data_clicked)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def apply(self) -> BrowserSettings:
        self._settings.update(
            dark_mode=self._dark_mode_checkbox.isChecked(),
            zoom_factor=self._zoom_spinbox.value(),
            adblock_enabled=self._adblock_checkbox.isChecked(),
            block_popups=self._block_popups_checkbox.isChecked(),
        )
        return self._settings

    def _on_clear_data_clicked(self) -> None:
        response = QMessageBox.question(
            self,
            "Clear site data",
            "This will remove all cookies, cached files, and other stored site data. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self.clearDataRequested.emit()
            QMessageBox.information(
                self,
                "Site data cleared",
                "All site data has been removed.",
            )


__all__ = ["BrowserWindow"]
