"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from html import escape
from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QUrl, Qt, QByteArray, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
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


_MEDIA_EXTENSIONS = (".mp4", ".m4v", ".mov")
_MEDIA_SCHEMES = {"http", "https", "file"}
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


def _is_media_url(url: QUrl) -> bool:
    if not url.isValid():
        return False
    scheme = url.scheme().lower()
    if scheme not in _MEDIA_SCHEMES:
        return False
    path = url.path().lower()
    return any(path.endswith(ext) for ext in _MEDIA_EXTENSIONS)


def _build_media_wrapper(url: QUrl) -> str | None:
    if not _is_media_url(url):
        return None

    safe_title = escape(url.fileName() or "MP4 Video")
    safe_src = escape(url.toString())
    LOGGER.info("Creating inline media wrapper for %s", safe_src)
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\">\n"
        f"    <title>{safe_title}</title>\n"
        "    <style>\n"
        "      :root {\n"
        "        color-scheme: dark;\n"
        "      }\n"
        "      body {\n"
        "        margin: 0;\n"
        "        background: #111;\n"
        "        color: #eee;\n"
        "        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;\n"
        "        display: flex;\n"
        "        align-items: center;\n"
        "        justify-content: center;\n"
        "        min-height: 100vh;\n"
        "      }\n"
        "      main {\n"
        "        width: 100%;\n"
        "        padding: 1rem;\n"
        "        box-sizing: border-box;\n"
        "      }\n"
        "      video {\n"
        "        display: block;\n"
        "        margin: 0 auto;\n"
        "        max-width: 100%;\n"
        "        max-height: calc(100vh - 2rem);\n"
        "        background: #000;\n"
        "      }\n"
        "      p {\n"
        "        text-align: center;\n"
        "        margin-top: 1rem;\n"
        "        font-size: 0.95rem;\n"
        "      }\n"
        "      a {\n"
        "        color: #8ab4f8;\n"
        "      }\n"
        "    </style>\n"
        "  </head>\n"
        "  <body>\n"
        "    <main>\n"
        "      <video controls autoplay playsinline preload=\"metadata\">\n"
        f"        <source src=\"{safe_src}\" type=\"video/mp4\">\n"
        "        <p>Your system cannot play this MP4 file. <a href=\""
        f"{safe_src}\">Download the video</a> instead.</p>\n"
        "      </video>\n"
        "    </main>\n"
        "  </body>\n"
        "</html>"
    )


class MediaAwareWebEnginePage(QWebEnginePage):
    """Page subclass that intercepts direct media navigations."""

    media_wrapper_requested = pyqtSignal(QUrl)
    media_wrapper_cleared = pyqtSignal()

    def __init__(self, parent: QWebEngineView | None = None) -> None:
        super().__init__(parent)
        self._current_media_source: str | None = None

    # pylint: disable=unused-argument
    def acceptNavigationRequest(
        self,
        url: QUrl,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if is_main_frame:
            html = _build_media_wrapper(url)
            if html is not None:
                url_string = url.toString()
                self._current_media_source = url_string
                self.media_wrapper_requested.emit(url)
                LOGGER.info("Intercepted media navigation: %s", url_string)
                self.setHtml(html, baseUrl=url)
                return False
            if self._current_media_source is not None:
                self._current_media_source = None
                self.media_wrapper_cleared.emit()
                LOGGER.info("Cleared media wrapper after navigating away")
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


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
        self.setCentralWidget(self._tab_widget)

        self._apply_dark_theme()

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
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setContentsMargins(4, 4, 4, 4)

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
    # Appearance
    # ------------------------------------------------------------------
    def _apply_dark_theme(self) -> None:
        """Apply a consistent dark appearance across the window."""

        dark_stylesheet = """
        QMainWindow {
            background-color: #070f1f;
            color: #e2e8f0;
        }

        QWidget {
            color: #e2e8f0;
            background-color: transparent;
            selection-background-color: #38bdf8;
            selection-color: #020617;
        }

        QToolBar {
            background-color: #0d182c;
            border: 0;
            border-bottom: 1px solid #1f2a3d;
            padding: 6px 8px;
            spacing: 6px;
        }

        QToolBar QToolButton {
            background: transparent;
            color: #f8fafc;
            border-radius: 8px;
            padding: 6px;
            margin: 0 2px;
        }

        QToolBar QToolButton:hover {
            background-color: rgba(148, 163, 184, 0.22);
        }

        QToolBar QToolButton:pressed,
        QToolBar QToolButton:checked,
        QToolBar QToolButton:focus {
            background-color: rgba(59, 130, 246, 0.4);
        }

        QLineEdit {
            background-color: #141f33;
            color: #f1f5f9;
            border: 1px solid #324059;
            border-radius: 14px;
            padding: 6px 14px;
            min-height: 30px;
        }

        QLineEdit:focus,
        QLineEdit:hover {
            border: 1px solid #38bdf8;
        }

        QTabWidget::pane {
            border-top: 1px solid #1b2638;
            background: #0a1324;
        }

        QTabWidget::tab-bar {
            left: 6px;
        }

        QTabBar::tab {
            background: #111d32;
            color: #cbd5f5;
            border: 1px solid transparent;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            padding: 8px 18px;
            margin-right: 4px;
            min-width: 96px;
        }

        QTabBar::tab:!selected {
            color: #9aa8c4;
            border-color: transparent;
            margin-top: 4px;
        }

        QTabBar::tab:selected {
            background: #1c2a41;
            color: #f8fafc;
            border-color: #3b82f6;
            margin-top: 0;
        }

        QTabBar::tab:hover {
            background: #16263d;
        }

        QTabWidget QToolButton {
            background: transparent;
            color: #f8fafc;
            border-radius: 8px;
            padding: 6px 12px;
        }

        QTabWidget QToolButton:hover {
            background-color: rgba(59, 130, 246, 0.3);
        }

        QStatusBar {
            background: #070f1f;
            color: #cbd5f5;
            border-top: 1px solid #1f2a3d;
        }

        QMenu {
            background-color: #101d33;
            border: 1px solid #24344d;
            padding: 6px;
        }

        QMenu::item {
            padding: 6px 18px;
            border-radius: 6px;
        }

        QMenu::item:selected {
            background-color: rgba(59, 130, 246, 0.35);
            color: #f8fafc;
        }

        QScrollBar:vertical {
            background: #0d182c;
            border: none;
            margin: 16px 0 16px 0;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar:horizontal {
            background: #0d182c;
            border: none;
            margin: 0 16px 0 16px;
            height: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {
            background: rgba(148, 163, 184, 0.45);
            border-radius: 6px;
        }

        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:horizontal:hover {
            background: rgba(148, 163, 184, 0.7);
        }

        QDialog,
        QMessageBox {
            background-color: #101d33;
        }

        QDialog QPushButton,
        QDialogButtonBox QPushButton,
        QMessageBox QPushButton {
            border-radius: 6px;
            padding: 6px 14px;
            background-color: #2563eb;
            color: #f8fafc;
        }

        QDialog QPushButton:hover,
        QDialogButtonBox QPushButton:hover,
        QMessageBox QPushButton:hover {
            background-color: #1d4ed8;
        }

        QPushButton:disabled,
        QToolButton:disabled {
            color: rgba(148, 163, 184, 0.4);
            background-color: transparent;
        }

        QToolTip {
            background-color: #1c2a41;
            color: #f8fafc;
            border: 1px solid #3b82f6;
            padding: 6px 10px;
            border-radius: 6px;
        }

        QListWidget,
        QAbstractItemView {
            background-color: rgba(13, 24, 44, 0.6);
            border: 1px solid #1f2a3d;
            selection-background-color: rgba(59, 130, 246, 0.5);
            selection-color: #f8fafc;
        }
        """

        self.setStyleSheet(dark_stylesheet)

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
        page = MediaAwareWebEnginePage(view)
        page.media_wrapper_requested.connect(
            lambda url, view=view: self._on_media_wrapper_requested(view, url)
        )
        page.media_wrapper_cleared.connect(
            lambda view=view: self._on_media_wrapper_cleared(view)
        )
        view.setPage(page)
        self._configure_web_view(view)
        LOGGER.info("Created web view with media-aware page")
        view.urlChanged.connect(lambda url, view=view: self._on_url_changed(view, url))
        view.loadFinished.connect(lambda ok, view=view: self._on_load_finished(view, ok))
        view.titleChanged.connect(lambda title, view=view: self._update_tab_title(view, title))
        view.iconChanged.connect(lambda icon, view=view: self._update_tab_icon(view, icon))
        return view

    def _add_tab(self, url: str | QUrl | None = None, *, focus: bool = True) -> QWebEngineView:
        view = self._create_web_view()
        index = self._tab_widget.addTab(view, "New Tab")
        if focus:
            self._tab_widget.setCurrentIndex(index)
        if isinstance(url, QUrl):
            target = url
        elif isinstance(url, str):
            target = QUrl.fromUserInput(url)
        else:
            target = self._start_page_url
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
        if self._maybe_embed_media(view, url):
            return
        if view is self._current_web_view():
            if url.toString() != self._address_bar.text():
                self._address_bar.setText(url.toString())

    def _on_load_finished(self, view: QWebEngineView, ok: bool) -> None:
        media_source = view.property("jenniebrowser_media_source")
        has_media_wrapper = isinstance(media_source, str)
        success = ok or has_media_wrapper
        if not success:
            LOGGER.warning(
                "Load failure for %s (wrapper=%s)",
                view.url().toString(),
                has_media_wrapper,
            )
        else:
            LOGGER.info(
                "Load finished for %s (wrapper=%s)",
                view.url().toString(),
                has_media_wrapper,
            )
        if view is self._current_web_view():
            if success:
                self._status_bar.showMessage("Loaded", 2000)
            else:
                self._status_bar.showMessage("Failed to load page", 4000)
                QMessageBox.warning(self, "Load Error", "The page could not be loaded.")
        if success:
            self._update_tab_title(view, view.title() or "New Tab")
            history_url = view.url().toString()
            if has_media_wrapper:
                history_url = str(media_source)
            self._history.add_entry(history_url, view.title())

    def _update_tab_title(self, view: QWebEngineView, title: str) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabText(index, title or "New Tab")

    def _update_tab_icon(self, view: QWebEngineView, icon: QIcon) -> None:
        index = self._tab_widget.indexOf(view)
        if index != -1:
            self._tab_widget.setTabIcon(index, icon)

    def _on_media_wrapper_requested(self, view: QWebEngineView, url: QUrl) -> None:
        view.setProperty("jenniebrowser_media_source", url.toString())
        if view is self._current_web_view():
            if url.toString() != self._address_bar.text():
                self._address_bar.setText(url.toString())
        LOGGER.info("Media wrapper active for %s", url.toString())

    def _on_media_wrapper_cleared(self, view: QWebEngineView) -> None:
        view.setProperty("jenniebrowser_media_source", None)
        LOGGER.info("Media wrapper cleared")

    def _maybe_embed_media(self, view: QWebEngineView, url: QUrl) -> bool:
        if isinstance(view.page(), MediaAwareWebEnginePage):
            # Media-aware pages manage wrapper lifecycles internally.
            if not _is_media_url(url) and view.property("jenniebrowser_media_source"):
                view.setProperty("jenniebrowser_media_source", None)
            return False

        html = _build_media_wrapper(url)
        if html is None:
            if view.property("jenniebrowser_media_source"):
                view.setProperty("jenniebrowser_media_source", None)
            return False

        view.setHtml(html, baseUrl=url)
        view.setProperty("jenniebrowser_media_source", url.toString())
        if view is self._current_web_view():
            url_string = url.toString()
            if url_string != self._address_bar.text():
                self._address_bar.setText(url_string)
        LOGGER.info("Embedded media wrapper manually for %s", url.toString())
        return True

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
