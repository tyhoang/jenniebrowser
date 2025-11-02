"""Main window and navigation controls for the JennieBrowser application."""

from __future__ import annotations

import logging
import shutil
import json
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Iterable, Optional, cast
from urllib.parse import quote_plus

from PyQt6.QtCore import QUrl, Qt, QByteArray, QEvent, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QMouseEvent, QKeyEvent, QCloseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QDoubleSpinBox,
    QProgressDialog,
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
    QWebEngineDownloadRequest,
    QWebEngineFullScreenRequest,
    QWebEngineNewWindowRequest,
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


_HINT_GATHER_SCRIPT = """
(() => {
    try {
        const previous = document.querySelectorAll('[data-jb-hint-id]');
        previous.forEach(el => {
            try {
                delete el.dataset.jbHintId;
            } catch (err) {
                el.removeAttribute('data-jb-hint-id');
            }
        });

        const selectors = [
            'a[href]',
            'button',
            'input[type="button"]',
            'input[type="submit"]',
            'input[type="reset"]',
            'input[type="image"]',
            '[role="button"]',
            '[onclick]',
            'summary',
            'label[for]',
            'area[href]'
        ].join(',');

        const elements = Array.from(document.querySelectorAll(selectors));
        const results = [];
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
        const limit = 400;
        let index = 0;

        for (const element of elements) {
            if (!element || !element.isConnected) {
                continue;
            }
            const rect = element.getBoundingClientRect();
            if (!rect || (rect.width <= 1 && rect.height <= 1)) {
                continue;
            }
            if (
                rect.bottom < 0 ||
                rect.top > viewportHeight ||
                rect.right < 0 ||
                rect.left > viewportWidth
            ) {
                continue;
            }
            const style = window.getComputedStyle(element);
            if (
                style.visibility === 'hidden' ||
                style.display === 'none' ||
                Number(style.opacity || '1') === 0
            ) {
                continue;
            }
            const id = 'jb-hint-' + index++;
            element.dataset.jbHintId = id;
            results.push({
                id: id,
                text: (element.getAttribute('aria-label') || element.title || element.alt || element.textContent || '').trim()
            });
            if (index >= limit) {
                break;
            }
        }
        return results;
    } catch (error) {
        console.warn('JennieBrowser hint gather failed', error);
        return [];
    }
})();
"""


_HINT_BOOTSTRAP_SCRIPT = """
(() => {
    if (window.jbHints && window.jbHints.initialized) {
        return;
    }

    const state = {
        overlay: null,
        items: [],
        style: null
    };

    function ensureStyle() {
        if (state.style && state.style.isConnected) {
            return;
        }
        const style = document.createElement('style');
        style.id = 'jb-hints-style';
        style.textContent = [
            '.jb-hint-label {',
            '  background: rgba(0, 0, 0, 0.85);',
            '  color: #f8f8f2;',
            '  border-radius: 3px;',
            '  padding: 1px 4px;',
            '  font-size: 12px;',
            '  font-family: \"Fira Code\", Menlo, Monaco, monospace;',
            '  position: absolute;',
            '  pointer-events: none;',
            '  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);',
            '}',
            '.jb-hint-hidden { display: none !important; }',
            '.jb-hint-highlight { background: #ffd866 !important; color: #000 !important; }'
        ].join('\\n');
        const root = document.head || document.documentElement;
        root.appendChild(style);
        state.style = style;
    }

    function ensureOverlay() {
        if (state.overlay && state.overlay.isConnected) {
            return state.overlay;
        }
        const overlay = document.createElement('div');
        overlay.id = 'jb-hint-overlay';
        overlay.style.position = 'absolute';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '0';
        overlay.style.height = '0';
        overlay.style.zIndex = '2147483647';
        overlay.style.pointerEvents = 'none';
        const parent = document.body || document.documentElement;
        parent.appendChild(overlay);
        state.overlay = overlay;
        return overlay;
    }

    function clearOverlay() {
        if (state.overlay) {
            state.overlay.innerHTML = '';
        }
    }

    function findElementById(id) {
        return document.querySelector('[data-jb-hint-id=\"' + id + '\"]');
    }

    window.jbHints = {
        initialized: true,
        set(items) {
            ensureStyle();
            const overlay = ensureOverlay();
            clearOverlay();
            state.items = Array.isArray(items) ? items.slice() : [];
            for (const item of state.items) {
                const element = findElementById(item.id);
                if (!element) {
                    continue;
                }
                const rect = element.getBoundingClientRect();
                const span = document.createElement('span');
                span.className = 'jb-hint-label';
                span.dataset.hintLabel = item.label;
                span.style.left = (rect.left + window.scrollX) + 'px';
                span.style.top = (rect.top + window.scrollY) + 'px';
                span.textContent = item.label;
                overlay.appendChild(span);
            }
            window.jbHints.reposition();
        },
        reposition() {
            if (!state.overlay || !state.items.length) {
                return;
            }
            for (const item of state.items) {
                const element = findElementById(item.id);
                const span = state.overlay.querySelector('[data-hint-label=\"' + item.label + '\"]');
                if (!element || !span) {
                    continue;
                }
                const rect = element.getBoundingClientRect();
                span.style.left = (rect.left + window.scrollX) + 'px';
                span.style.top = (rect.top + window.scrollY) + 'px';
            }
        },
        filter(prefix) {
            if (!state.overlay) {
                return 0;
            }
            const normalized = (prefix || '').toLowerCase();
            let visible = 0;
            const spans = state.overlay.querySelectorAll('.jb-hint-label');
            spans.forEach(span => {
                const label = (span.dataset.hintLabel || '').toLowerCase();
                if (!normalized || label.startsWith(normalized)) {
                    span.classList.remove('jb-hint-hidden');
                    if (normalized && label === normalized) {
                        span.classList.add('jb-hint-highlight');
                    } else {
                        span.classList.remove('jb-hint-highlight');
                    }
                    visible += 1;
                } else {
                    span.classList.add('jb-hint-hidden');
                    span.classList.remove('jb-hint-highlight');
                }
            });
            return visible;
        },
        hide() {
            if (state.overlay) {
                state.overlay.remove();
                state.overlay = null;
            }
            state.items = [];
        },
        activate(label) {
            if (!label) {
                return false;
            }
            const target = (state.items || []).find(item => item.label === label);
            if (!target) {
                return false;
            }
            const element = findElementById(target.id);
            if (!element) {
                return false;
            }
            if (typeof element.focus === 'function') {
                try {
                    element.focus({ preventScroll: true });
                } catch (err) {
                    try {
                        element.focus();
                    } catch (inner) {
                        /* ignore */
                    }
                }
            }
            const event = new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
            });
            element.dispatchEvent(event);
            return true;
        }
    };

    window.addEventListener('scroll', () => window.jbHints.reposition(), { passive: true });
    window.addEventListener('resize', () => window.jbHints.reposition());
})();
"""

@dataclass
class _PendingNewWindowRequest:
    user_initiated: bool
    requested_url: QUrl | None


class BrowserWebView(QWebEngineView):
    """Custom ``QWebEngineView`` that integrates with the tabbed UI."""

    def __init__(self, browser_window: "BrowserWindow") -> None:
        super().__init__(browser_window)
        self._browser_window = browser_window
        self.page().newWindowRequested.connect(
            self._browser_window._on_new_window_requested
        )

    # Qt calls this when a page requests a new window (e.g. "open link in new tab").
    def createWindow(  # pylint: disable=invalid-name
        self, window_type: QWebEnginePage.WebWindowType
    ) -> QWebEngineView:  # type: ignore[override]
        """Return a tab for window creation requests triggered by web content."""
        focus = window_type != QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        LOGGER.info("createWindow requested with type %s", window_type)
        return self._browser_window.open_tab_for_new_window(focus)

    def keyPressEvent(  # pylint: disable=invalid-name
        self, event: QKeyEvent
    ) -> None:  # type: ignore[override]
        """Let the browser consume hint shortcuts before deferring to Qt."""
        if self._browser_window.process_hint_keypress(event):
            return
        if (
            event.key() == Qt.Key.Key_F
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            if self._browser_window.request_hint_mode(self):
                event.accept()
                return
        super().keyPressEvent(event)
class BrowserWindow(QMainWindow):  # pylint: disable=too-many-instance-attributes
    """Single window browser with a minimal user interface."""

    # pylint: disable=too-many-arguments,too-many-statements
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
        self._block_popups = self._settings.block_popups
        self._active_downloads: list[DownloadProgressDialog] = []
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
        self._tab_widget.setCornerWidget(
            self._new_tab_button,
            Qt.Corner.TopRightCorner,
        )

        self._adblocker = self._install_adblocker(
            rule_paths,
            self._settings.adblock_enabled and adblock_enabled,
        )

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        self._pending_new_window_request: QWebEngineNewWindowRequest | None = None

        self._hint_mode_active = False
        self._hint_buffer = ""
        self._hint_targets: Dict[str, str] = {}
        self._hint_source_view: Optional[QWebEngineView] = None

        self._find_bar = QLineEdit(self)
        self._find_bar.setPlaceholderText("Find in page")
        self._find_bar.setClearButtonEnabled(True)
        self._find_bar.setMaximumWidth(240)
        self._find_bar.returnPressed.connect(self._find_next)
        self._find_bar.textChanged.connect(self._on_find_text_changed)
        self._find_bar.installEventFilter(self)
        self._find_bar.hide()
        self._status_bar.addPermanentWidget(self._find_bar)
        self._last_find_text = ""

        self._address_bar = QLineEdit(self)
        self._address_bar.setClearButtonEnabled(True)
        self._address_bar.returnPressed.connect(self._on_url_entered)
        self._address_bar.setPlaceholderText("Enter URL or search term…")
        self._address_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._toolbar = self._build_toolbar()
        self.addToolBar(self._toolbar)

        self._apply_privacy_defaults()
        profile = QWebEngineProfile.defaultProfile()
        profile.downloadRequested.connect(self._on_download_requested)
        self._shortcuts = []
        self._is_fullscreen = False
        self._stored_geometry: QByteArray | None = None
        self._install_shortcuts()
        self._apply_settings()
        self._initialise_tabs(start_url)

    # ------------------------------------------------------------------
    # Toolbar & actions
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

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

        home_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon),
            "Home",
            self,
        )
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
        """Navigate the active tab to the configured homepage."""
        self._load_url(self._homepage)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_url_entered(self) -> None:
        text = self._address_bar.text().strip()
        if not text:
            return

        url = QUrl.fromUserInput(text)
        if self._looks_like_url(text, url):
            self._load_url(url)
        else:
            self._perform_search(text)

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
    def _perform_search(self, text: str) -> None:
        query = quote_plus(text)
        search_url = f"https://duckduckgo.com/?q={query}"
        self._load_url(search_url)

    def _load_url(self, value: str | QUrl) -> None:
        self._exit_hint_mode()
        if isinstance(value, QUrl):
            url = value
        else:
            url = QUrl.fromUserInput(value)
        if not url.isValid():
            QMessageBox.warning(self, "Invalid URL", "The address you entered is not valid.")
            return
        view = self._current_web_view()
        if view is None:
            view = self._add_tab(url.toString())
        else:
            view.setUrl(url)

    def _looks_like_url(self, text: str, url: QUrl | None = None) -> bool:
        if " " in text:
            return False

        candidate = url or QUrl.fromUserInput(text)
        if not candidate.isValid():
            return False

        scheme = candidate.scheme().lower()
        if scheme in {"http", "https", "ftp"}:
            host = candidate.host()
            if not host:
                looks_like_host = False
            elif host == "localhost":
                looks_like_host = True
            elif host.replace(".", "").isdigit():
                looks_like_host = True
            else:
                parts = [part for part in host.split(".") if part]
                looks_like_host = len(parts) >= 2 and parts[-1].isalpha()
            return looks_like_host

        if scheme in {"file", "about", "data"}:
            return True

        return False

    def _install_adblocker(self, rule_paths: Iterable[Path], enabled: bool) -> AdBlocker:
        rule_set = RuleSet.from_paths(rule_paths)
        adblocker = AdBlocker(rule_set, enabled=enabled)
        profile: QWebEngineProfile = QWebEngineProfile.defaultProfile()
        profile.setUrlRequestInterceptor(adblocker)
        return adblocker

    def _on_download_requested(self, download: QWebEngineDownloadRequest) -> None:
        if download.state() != QWebEngineDownloadRequest.DownloadState.DownloadRequested:
            return

        suggested_name = download.downloadFileName() or "download"
        default_target = Path.home() / suggested_name
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            str(default_target),
        )
        if not target_path:
            download.cancel()
            self._status_bar.showMessage("Download cancelled", 2000)
            return

        target = Path(target_path)
        try:
            download.setDownloadDirectory(str(target.parent))
            download.setDownloadFileName(target.name)
        except AttributeError:
            download.setPath(str(target))

        download.accept()
        dialog = DownloadProgressDialog(download, self)
        self._active_downloads.append(dialog)
        dialog.finished.connect(
            lambda _result, dlg=dialog: self._remove_download_dialog(dlg)
        )
        download.finished.connect(lambda: self._on_download_finished(download))
        dialog.show()
        self._status_bar.showMessage(f"Downloading {target.name}", 2000)

    def _on_download_finished(self, download: QWebEngineDownloadRequest) -> None:
        state = download.state()
        name = download.downloadFileName() or "download"
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self._status_bar.showMessage(f"Downloaded {name}", 4000)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self._status_bar.showMessage("Download cancelled", 2000)
        else:
            self._status_bar.showMessage(f"Download failed for {name}", 4000)

    def _remove_download_dialog(self, dialog: QProgressDialog) -> None:
        if dialog in self._active_downloads:
            self._active_downloads.remove(dialog)
        dialog.deleteLater()

    def _on_new_window_requested(self, request: QWebEngineNewWindowRequest) -> None:
        if self._block_popups and not request.isUserInitiated():
            url = request.requestedUrl().toString()
            LOGGER.info("Blocked scripted new window request for %s", url)
            self._status_bar.showMessage("Blocked a pop-up", 3000)
            request.reject()
            self._pending_new_window_request = None
            return

        LOGGER.info(
            "Received new window request (user initiated=%s, destination=%s)",
            request.isUserInitiated(),
            request.destination(),
        )
        self._pending_new_window_request = request

    def _handle_new_window_request(
        self, window_type: QWebEnginePage.WebWindowType
    ) -> QWebEngineView | None:
        tab_types = {
            QWebEnginePage.WebWindowType.WebBrowserTab,
            QWebEnginePage.WebWindowType.WebBrowserBackgroundTab,
        }

        request = self._pending_new_window_request
        self._pending_new_window_request = None

        if (
            request is not None
            and self._block_popups
            and not request.isUserInitiated()
        ):
            LOGGER.info(
                "Blocked new window request of type %s due to pop-up settings",
                window_type,
            )
            self._status_bar.showMessage("Blocked a pop-up", 3000)
            request.reject()
            return None

        if self._block_popups and window_type not in tab_types:
            LOGGER.info("Blocked new window request of type %s", window_type)
            self._status_bar.showMessage("Blocked a pop-up", 3000)
            if request is not None:
                request.reject()
            return None

        focus = window_type != QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        view = self._add_tab(
            None,
            focus=focus,
            load_default_url=False,
        )
        if request is not None:
            if hasattr(request, "accept"):
                request.accept()
            open_in = getattr(request, "openIn", None)
            if callable(open_in):
                open_in(view)
            LOGGER.info(
                "Allowing new window request of type %s (user initiated=%s)",
                window_type,
                request.isUserInitiated(),
            )
        else:
            LOGGER.info("Allowing new window request of type %s", window_type)
        return view

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
            (QKeySequence("Ctrl+F"), self._show_find_bar),
            (QKeySequence("F3"), self._find_next),
            (QKeySequence("Shift+F3"), self._find_previous),
        ]
        for sequence, handler in mappings:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)  # type: ignore[arg-type]
            self._shortcuts.append(shortcut)

    def _focus_address_bar(self) -> None:
        self._exit_hint_mode()
        self._address_bar.setFocus()
        self._address_bar.selectAll()

    def _clear_text_focus(self) -> None:
        self._hide_find_bar()
        self._exit_hint_mode()
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

    def _show_find_bar(self) -> None:
        if not self._find_bar.isVisible():
            self._find_bar.show()
        if self._last_find_text and not self._find_bar.text():
            self._find_bar.setText(self._last_find_text)
            self._find_bar.selectAll()
        self._find_bar.setFocus()

    def _hide_find_bar(self) -> None:
        if not self._find_bar.isVisible():
            return
        self._find_bar.hide()
        view = self._current_web_view()
        if view is not None:
            view.findText("")

    def _find_next(self) -> None:
        text = self._find_bar.text().strip() or self._last_find_text
        if not text:
            return
        self._last_find_text = text
        self._find_in_page(text, forward=True)

    def _find_previous(self) -> None:
        text = self._find_bar.text().strip() or self._last_find_text
        if not text:
            return
        self._last_find_text = text
        self._find_in_page(text, forward=False)

    def _find_in_page(self, text: str, *, forward: bool) -> None:
        view = self._current_web_view()
        if view is None:
            return
        if not text:
            view.findText("")
            return
        flags = QWebEnginePage.FindFlag(0)
        if not forward:
            flags |= QWebEnginePage.FindFlag.FindBackward
        view.findText(text, flags)

    def _on_find_text_changed(self, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            self._last_find_text = ""
            view = self._current_web_view()
            if view is not None:
                view.findText("")
            return
        self._last_find_text = stripped
        self._find_in_page(stripped, forward=True)

    # ------------------------------------------------------------------
    # Hint mode helpers
    # ------------------------------------------------------------------
    def _trigger_hint_mode(self, view: QWebEngineView) -> bool:
        if view is None:
            return False
        if self._hint_mode_active:
            return True
        self._hide_find_bar()
        self._collect_hint_targets(view)
        return True

    def _collect_hint_targets(self, view: QWebEngineView) -> None:
        page = view.page()
        page.runJavaScript(
            _HINT_GATHER_SCRIPT,
            0,
            lambda result, v=view: self._on_hint_candidates(v, result),
        )

    def request_hint_mode(self, view: QWebEngineView) -> bool:
        """Entry point for hint mode requests initiated by embedded web views."""
        return self._trigger_hint_mode(view)

    def _on_hint_candidates(self, view: QWebEngineView, result: object) -> None:
        if self._hint_source_view is not None and self._hint_source_view is not view:
            return
        items: list[dict[str, object]] = []
        if isinstance(result, list):
            for entry in result:
                if isinstance(entry, dict) and "id" in entry:
                    items.append(entry)
        if not items:
            self._status_bar.showMessage("No clickable targets found", 2000)
            return
        labels = self._generate_hint_labels(len(items))
        mapping: Dict[str, str] = {}
        payload: list[dict[str, str]] = []
        for entry, label in zip(items, labels):
            target_id = str(entry.get("id", ""))
            mapping[label] = target_id
            payload.append({"id": target_id, "label": label})
        self._hint_mode_active = True
        self._hint_buffer = ""
        self._hint_targets = mapping
        self._hint_source_view = view
        self._status_bar.showMessage("Hint mode: type label to follow link (Esc to cancel)", 3000)
        self._show_hint_overlay(view, payload)

    @staticmethod
    def _generate_hint_labels(count: int) -> list[str]:
        alphabet = list("asdfghjklqwertyuiopzxcvbnm")
        if count <= 0:
            return []
        if count <= len(alphabet):
            return alphabet[:count]
        labels = alphabet[:]
        remaining = count - len(alphabet)
        combinations: list[str] = []
        for first in alphabet:
            for second in alphabet:
                combinations.append(first + second)
                if len(combinations) >= remaining:
                    break
            if len(combinations) >= remaining:
                break
        labels.extend(combinations[:remaining])
        return labels[:count]

    def _show_hint_overlay(self, view: QWebEngineView, payload: list[dict[str, str]]) -> None:
        data = json.dumps(payload)

        def apply_overlay(_ignored: object) -> None:
            view.page().runJavaScript(
                (
                    f"window.jbHints && window.jbHints.set({data}); "
                    "window.jbHints && window.jbHints.filter('');"
                ),
                0,
            )

        view.page().runJavaScript(_HINT_BOOTSTRAP_SCRIPT, 0, apply_overlay)

    def _update_hint_filter(self) -> None:
        if self._hint_source_view is None:
            return
        prefix = json.dumps(self._hint_buffer)
        self._hint_source_view.page().runJavaScript(
            f"window.jbHints ? window.jbHints.filter({prefix}) : 0;",
            0,
        )

    def _activate_hint_label(self, label: str) -> None:
        view = self._hint_source_view
        if view is None:
            self._exit_hint_mode()
            return

        script = f"window.jbHints ? window.jbHints.activate({json.dumps(label)}) : false;"

        def after_activation(result: object) -> None:
            if not result:
                self._status_bar.showMessage("Unable to follow hint", 2000)
            self._exit_hint_mode()

        view.page().runJavaScript(script, 0, after_activation)

    def _exit_hint_mode(self) -> None:
        if not self._hint_mode_active and self._hint_source_view is None:
            return
        view = self._hint_source_view
        self._hint_mode_active = False
        self._hint_buffer = ""
        self._hint_targets = {}
        self._hint_source_view = None
        if view is not None:
            view.page().runJavaScript(
                "window.jbHints && window.jbHints.hide && window.jbHints.hide();",
                0,
            )

    def _handle_hint_keypress(self, event: QKeyEvent) -> bool:
        if not self._hint_mode_active:
            return False

        key = event.key()
        event.accept()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Cancel):
            self._status_bar.showMessage("Hint mode cancelled", 1500)
            self._exit_hint_mode()
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_unique_hint_match()
            return True

        if key == Qt.Key.Key_Backspace:
            self._handle_hint_backspace()
            return True

        text = event.text()
        if text:
            self._handle_hint_character(text.lower())
        return True

    def _activate_unique_hint_match(self) -> None:
        """Follow the sole matching hint when the user presses Enter."""
        matches = [
            label for label in self._hint_targets if label.startswith(self._hint_buffer)
        ]
        if len(matches) == 1:
            self._activate_hint_label(matches[0])

    def _handle_hint_backspace(self) -> None:
        """Adjust the hint buffer when the user presses Backspace."""
        if self._hint_buffer:
            self._hint_buffer = self._hint_buffer[:-1]
            self._update_hint_filter()
        else:
            self._exit_hint_mode()

    def _handle_hint_character(self, char: str) -> None:
        """Append alphabetic characters and react to the resulting matches."""
        if not char.isalpha():
            return
        self._hint_buffer += char
        matches = [
            label for label in self._hint_targets if label.startswith(self._hint_buffer)
        ]
        if not matches:
            self._status_bar.showMessage("No matching hint", 1500)
            self._hint_buffer = ""
            self._update_hint_filter()
            return
        self._update_hint_filter()
        if self._hint_buffer in self._hint_targets:
            self._activate_hint_label(self._hint_buffer)

    def process_hint_keypress(self, event: QKeyEvent) -> bool:
        """Allow delegated key events from web views to reuse hint-mode logic."""
        return self._handle_hint_keypress(event)

    def _scroll_down(self) -> None:
        view = self._current_web_view()
        if view is None:
            return
        view.page().runJavaScript(
            "window.scrollBy({top: 120, left: 0, behavior: 'smooth'});"
        )

    def _scroll_up(self) -> None:
        view = self._current_web_view()
        if view is None:
            return
        view.page().runJavaScript(
            "window.scrollBy({top: -120, left: 0, behavior: 'smooth'});"
        )

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
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
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
            dark_value = getattr(
                color_scheme_enum,
                "Dark",
                getattr(color_scheme_enum, "ColorSchemeDark", None),
            )
            light_value = getattr(
                color_scheme_enum,
                "Light",
                getattr(color_scheme_enum, "ColorSchemeLight", None),
            )
            if dark_value is not None and light_value is not None:
                profile.setColorScheme(dark_value if self._settings.dark_mode else light_value)
        for view in self._iter_web_views():
            view.setZoomFactor(self._settings.zoom_factor)
        self._adblocker.set_enabled(self._settings.adblock_enabled)
        self._block_popups = self._settings.block_popups

    def _initialise_tabs(self, start_url: QUrl | str | None) -> None:
        targets, focus_index = self._resolve_initial_tab_targets(start_url)
        views: list[QWebEngineView] = []
        for target in targets:
            view = self._add_tab(target, focus=False)
            views.append(view)
        if not views:
            views.append(self._add_tab(self._start_page_url, focus=True))
            focus_index = 0
        focus_index = min(max(focus_index, 0), len(views) - 1)
        self._tab_widget.setCurrentIndex(focus_index)
        self._on_current_tab_changed(self._tab_widget.currentIndex())

    def _resolve_initial_tab_targets(
        self,
        start_url: QUrl | str | None,
    ) -> tuple[list[QUrl | str], int]:
        if start_url:
            return ([start_url], 0)
        if self._settings.restore_session and self._settings.last_session:
            targets: list[str | QUrl] = []
            for item in self._settings.last_session:
                text = str(item).strip()
                if text:
                    targets.append(text)
            if targets:
                index = min(self._settings.last_session_index, len(targets) - 1)
                return (targets, index)
        return ([self._start_page_url], 0)

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
        view.page().newWindowRequested.connect(self._on_new_window_requested)
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

    def open_tab_for_new_window(self, focus: bool) -> QWebEngineView:
        """Provision a tab for a new-window request originating from web content."""
        return self._add_tab(
            None,
            focus=focus,
            load_default_url=False,
        )

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
                fallback_url = (
                    self._start_page_url
                    if self._start_page_url.isValid()
                    else QUrl("about:blank")
                )
                view.setUrl(fallback_url)
                self._tab_widget.setTabText(index, "New Tab")
                self._tab_widget.setTabIcon(index, QIcon())
            self._address_bar.clear()
            return
        widget = self._tab_widget.widget(index)
        self._tab_widget.removeTab(index)
        if widget is not None:
            widget.deleteLater()

    def keyPressEvent(  # pylint: disable=invalid-name
        self, event: QKeyEvent
    ) -> None:  # type: ignore[override]
        """Handle window-level hint shortcuts before passing to Qt."""
        if self._handle_hint_keypress(event):
            return
        if (
            event.key() == Qt.Key.Key_F
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            view = self._current_web_view()
            if view is not None and self._trigger_hint_mode(view):
                event.accept()
                return
        super().keyPressEvent(event)

    def closeEvent(  # pylint: disable=invalid-name
        self, event: QCloseEvent
    ) -> None:  # type: ignore[override]
        """Store session state prior to closing the window."""
        self._save_session()
        super().closeEvent(event)

    def _save_session(self) -> None:
        if not self._settings.restore_session:
            self._settings.store_session([], 0)
            return
        urls: list[str] = []
        for view in self._iter_web_views():
            current = view.url().toString()
            if current:
                urls.append(current)
        current_index = self._tab_widget.currentIndex()
        self._settings.store_session(urls, current_index)

    def _on_current_tab_changed(self, _index: int) -> None:
        self._exit_hint_mode()
        view = self._current_web_view()
        if view is None:
            self._address_bar.clear()
            return
        self._address_bar.setText(view.url().toString())
        view.setFocus()

    def _on_url_changed(self, view: QWebEngineView, url: QUrl) -> None:
        if view is self._hint_source_view:
            self._exit_hint_mode()
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

    def eventFilter(  # pylint: disable=invalid-name
        self, obj: QObject, event: QEvent
    ) -> bool:
        """Enable middle-click closing on tab bar and pass through other events."""
        if obj is self._tab_widget.tabBar() and event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = cast(QMouseEvent, event)
            if mouse_event.button() == Qt.MouseButton.MiddleButton:
                tab_index = self._tab_widget.tabBar().tabAt(mouse_event.position().toPoint())
                if tab_index != -1:
                    self._close_tab(tab_index)
                    return True
        if obj is self._find_bar and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            if key_event.key() == Qt.Key.Key_Escape:
                self._hide_find_bar()
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


class DownloadProgressDialog(QProgressDialog):  # pylint: disable=too-few-public-methods
    """Lightweight progress dialog bound to a single download request."""

    def __init__(
        self,
        download: QWebEngineDownloadRequest,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__("Downloading…", "Cancel", 0, 100, parent)
        self._download = download
        self.setWindowTitle(download.downloadFileName() or "Download")
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setMinimumDuration(0)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setValue(0)
        self.setLabelText("Preparing download…")
        download.downloadProgress.connect(self._on_progress)
        download.finished.connect(self._on_finished)
        self.canceled.connect(self._on_cancel)

    def _on_progress(self, received: int, total: int) -> None:
        if total <= 0:
            self.setRange(0, 0)
            self.setLabelText(f"{received / (1024 * 1024):.1f} MB downloaded")
            return
        if self.maximum() == 0:
            self.setRange(0, 100)
        percent = int((received / total) * 100) if total else 0
        self.setValue(percent)
        total_mb = total / (1024 * 1024)
        received_mb = received / (1024 * 1024)
        self.setLabelText(f"{received_mb:.1f} MB of {total_mb:.1f} MB ({percent}%)")

    def _on_finished(self) -> None:
        self.setValue(self.maximum())
        self.close()

    def _on_cancel(self) -> None:
        self._download.cancel()


class HistoryDialog(QDialog):  # pylint: disable=too-few-public-methods
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
        _previous: QListWidgetItem | None,
    ) -> None:
        """Toggle whether the open button is active based on selection."""
        self._open_button.setEnabled(current is not None)

    def selected_url(self) -> str:
        """Return the currently highlighted URL or an empty string."""
        item = self._list.currentItem()
        if item is None:
            return ""
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data is not None else ""

    def accept(self) -> None:  # type: ignore[override]
        """Only accept the dialog when a URL is selected."""
        if self.selected_url():
            super().accept()


class SettingsDialog(QDialog):  # pylint: disable=too-few-public-methods
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

        self._popup_checkbox = QCheckBox("Block pop-ups", self)
        self._popup_checkbox.setChecked(settings.block_popups)

        self._restore_session_checkbox = QCheckBox("Restore tabs from last session", self)
        self._restore_session_checkbox.setChecked(settings.restore_session)

        form_layout = QFormLayout()
        form_layout.addRow(self._dark_mode_checkbox)
        form_layout.addRow("Zoom", self._zoom_spinbox)
        form_layout.addRow(self._adblock_checkbox)
        form_layout.addRow(self._popup_checkbox)
        form_layout.addRow(self._restore_session_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
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
        """Return an updated settings object capturing the dialog state."""
        self._settings.update(
            dark_mode=self._dark_mode_checkbox.isChecked(),
            zoom_factor=self._zoom_spinbox.value(),
            adblock_enabled=self._adblock_checkbox.isChecked(),
            block_popups=self._popup_checkbox.isChecked(),
            restore_session=self._restore_session_checkbox.isChecked(),
        )
        return self._settings

    def _on_clear_data_clicked(self) -> None:
        """Emit a request to clear stored site data after user confirmation."""
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
