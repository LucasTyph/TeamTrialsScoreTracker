"""The desktop app: main window, capture hotkey and clipboard watching.

``run()`` is the program's entry point (``python -m score_tracker``).
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import sys
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import ocr
from ..analysis import analyze
from ..capture import CaptureError, capture_game, game_in_front
from ..config import ASSETS_DIR, Settings, SettingsError, load_settings, save_settings
from ..pipeline import detect_roster
from ..session import MatchSession
from ..storage import append_match, delete_match, load_scores, migrate_legacy
from . import theme
from .analysis_page import AnalysisPage
from .match_page import MatchPage
from .roster_page import RosterPage
from .widgets import Toast, label, qimage_to_pil

logger = logging.getLogger(__name__)

APP_NAME = "Team Trials Score Tracker"
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x5354
_MODS = {"ctrl": 0x2, "control": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8}
_NAMED_KEYS = {"space": 0x20, "insert": 0x2D, "home": 0x24, "end": 0x23, "pause": 0x13,
               "printscreen": 0x2C, "pageup": 0x21, "pagedown": 0x22}


def parse_hotkey(text: str):
    """'ctrl+alt+s' -> (modifiers, virtual key), or None if invalid."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            return None
        mods |= _MODS[p]
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in _NAMED_KEYS:
        vk = _NAMED_KEYS[key]
    else:
        return None
    return mods, vk


class _JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _JobSignals()

    def run(self):
        try:
            self.signals.done.emit(self.fn(*self.args))
        except Exception as e:  # noqa: BLE001 - reported to the user
            logger.exception("Background job failed")
            self.signals.failed.emit(str(e))


class MainWindow(QMainWindow):
    hotkey_pressed = Signal()
    closing = Signal()  # emitted (synchronously) before the window closes

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "icon.png")))
        self.resize(1180, 820)
        self.setMinimumSize(900, 600)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(4)
        logo = label()
        logo.setPixmap(QPixmap(str(ASSETS_DIR / "icon.png")).scaledToHeight(40))
        side.addWidget(logo)
        side.addWidget(label("Score Tracker", "appTitle"))
        side.addWidget(label("Team Trials", "appSubtitle"))
        side.addSpacing(18)

        self.pages = QStackedWidget()
        self.match_page = MatchPage()
        self.analysis_page = AnalysisPage()
        self.roster_page = RosterPage()
        self.nav = QButtonGroup(self)
        self.nav_buttons = []
        for i, (text, page) in enumerate((("Current match", self.match_page),
                                          ("Analysis", self.analysis_page),
                                          ("Roster", self.roster_page))):
            self.pages.addWidget(page)
            b = QPushButton(text)
            b.setObjectName("navButton")
            b.setCheckable(True)
            self.nav.addButton(b, i)
            self.nav_buttons.append(b)
            side.addWidget(b)
        self.nav.idClicked.connect(self.pages.setCurrentIndex)
        self.nav_buttons[0].setChecked(True)
        side.addStretch(1)
        self.status = label("", "faint", wrap=True)
        side.addWidget(self.status)
        lay.addWidget(sidebar)
        lay.addWidget(self.pages, 1)

        self.toast = Toast(self)

    def show_page(self, index):
        self.nav_buttons[index].setChecked(True)
        self.pages.setCurrentIndex(index)
        if self.isMinimized():
            self.showNormal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toast.reposition()

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            import ctypes.wintypes as wt
            msg = wt.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.hotkey_pressed.emit()
                return True, 0
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)


class TrackerApp(QObject):
    match_saved = Signal(object)  # SavedMatch, emitted from any thread

    def __init__(self, app: QApplication, settings: Settings):
        super().__init__()
        self.app = app
        self.settings = settings
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)  # one OCR job at a time, in order
        self.busy = 0
        self.last_saved = None
        self.watch_clipboard = True
        self._last_clip_hash = None
        self._storage_lock = threading.Lock()
        self._hotkey_registered = False
        self._shut_down = False

        self.session = MatchSession(settings, on_save=self._store)
        self.match_saved.connect(self._on_saved)

        self.window = MainWindow()
        self.window.hotkey_pressed.connect(self.capture)
        self.window.closing.connect(self.shutdown)
        mp = self.window.match_page
        mp.capture_requested.connect(self.capture)
        mp.save_requested.connect(lambda: self.session.save())
        mp.discard_requested.connect(self._discard)
        mp.resolve_requested.connect(self._resolve)
        mp.ignore_row_requested.connect(self._ignore_row)
        mp.clipboard_toggled.connect(self._set_watch)
        rp = self.window.roster_page
        rp.settings_saved.connect(self._apply_settings)
        rp.detect_requested.connect(self._detect_roster)
        self.window.analysis_page.delete_match_requested.connect(self._delete_match)

        QGuiApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self._remember_clipboard()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.session.check_timeout)
        self.timer.start(30_000)

        self._register_hotkey()
        self.refresh_all()

    def notify(self, title, message="", kind="info"):
        logger.info("Notify: %s - %s", title, message.replace("\n", " | "))
        self.window.toast.show_message(title, message, kind)

    # --- hotkey -------------------------------------------------------------

    def _register_hotkey(self):
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        hwnd = int(self.window.winId())
        if self._hotkey_registered:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID)
            self._hotkey_registered = False
        parsed = parse_hotkey(self.settings.capture_hotkey)
        if parsed is None:
            self.notify("Hotkey not set", f"“{self.settings.capture_hotkey}” isn't a valid hotkey. "
                                          "Fix it on the Roster page.", "warning")
            return
        mods, vk = parsed
        if user32.RegisterHotKey(hwnd, HOTKEY_ID, mods | 0x4000, vk):  # MOD_NOREPEAT
            self._hotkey_registered = True
        else:
            self.notify("Hotkey unavailable", f"{self.settings.capture_hotkey.upper()} is used by another "
                                              "program. Pick another one on the Roster page.", "warning")

    # --- capturing ------------------------------------------------------------

    def capture(self):
        try:
            img = capture_game(self.settings.game_process)
        except CaptureError as e:
            self.notify("Couldn't capture the game", str(e), "error")
            return
        self.process(img)

    def _remember_clipboard(self):
        mime = QGuiApplication.clipboard().mimeData()
        if mime is not None and mime.hasImage():
            img = qimage_to_pil(QGuiApplication.clipboard().image())
            self._last_clip_hash = self._hash(img)

    @staticmethod
    def _hash(img):
        return hashlib.md5(img.resize((50, 50)).convert("L").tobytes()).hexdigest()

    def _set_watch(self, on):
        self.watch_clipboard = on
        if on:
            self._remember_clipboard()
        self.refresh_match()

    def _clipboard_changed(self):
        if not self.watch_clipboard:
            return
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage():
            return
        qimg = QGuiApplication.clipboard().image()
        if qimg.isNull():
            return
        img = qimage_to_pil(qimg)
        h = self._hash(img)
        if h == self._last_clip_hash:
            return
        self._last_clip_hash = h
        self.process(img)

    def process(self, img):
        self.busy += 1
        self.refresh_match()
        job = _Job(self.session.process_image, img)
        job.signals.done.connect(self._processed)
        job.signals.failed.connect(self._failed)
        self.pool.start(job)

    def _processed(self, outcome):
        self.busy -= 1
        if outcome.ignored:
            self.notify("No scores found", "That screenshot doesn't look like a Score Info screen.", "warning")
        else:
            completed = any(s.complete for s in outcome.saved)
            if not completed:
                review = len(self.session.pending.needs_review)
                extra = f" · {review} row(s) to review" if review else ""
                self.notify("Screenshot read",
                            f"{outcome.new_characters} new · {outcome.found}/{outcome.total} found{extra}")
        self.refresh_match()

    def _failed(self, message):
        self.busy -= 1
        self.notify("Something went wrong", message, "error")
        self.refresh_match()

    # --- saving -------------------------------------------------------------

    def _store(self, saved):
        """Called by the session (possibly on the worker thread)."""
        with self._storage_lock:
            append_match(saved.scores, self.settings, saved.distances)
        self.match_saved.emit(saved)

    def _on_saved(self, saved):
        self.last_saved = saved
        if self._shut_down:
            return
        total = sum(saved.scores.values())
        title = "Match saved" if saved.complete else "Partial match saved"
        detail = f"{len(saved.scores)} characters · total {total:,}"
        if saved.inferred:
            detail += "\nMatched by elimination: " + ", ".join(n for n, _ in saved.inferred)
        self.notify(title, detail, "success" if saved.complete else "info")
        # Flash the taskbar button when you're in the game rather than here
        if game_in_front(self.settings.game_process) or not self.window.isActiveWindow():
            QApplication.alert(self.window)
        self.refresh_all()

    def _discard(self):
        self.session.discard()
        self.refresh_match()

    def _resolve(self, name, score, row):
        self.session.resolve(name, score, row)
        self.refresh_match()

    def _ignore_row(self, row):
        self.session.pending.discard_row(row)
        self.refresh_match()

    def _delete_match(self, match_id):
        with self._storage_lock:
            delete_match(match_id, self.settings)
        self.refresh_analysis()

    # --- settings -------------------------------------------------------------

    def _apply_settings(self, settings):
        save_settings(settings)
        hotkey_changed = settings.capture_hotkey != self.settings.capture_hotkey
        self.settings = settings
        self.session.update_settings(settings)
        if hotkey_changed:
            self._register_hotkey()
        self.refresh_all()

    def _detect_roster(self):
        try:
            img = capture_game(self.settings.game_process)
        except CaptureError as e:
            self.window.roster_page.status.setText(f"Couldn't capture the game: {e}")
            return
        self.window.roster_page.status.setText("Reading names…")
        job = _Job(detect_roster, [img], self.settings)
        job.signals.done.connect(self._roster_detected)
        job.signals.failed.connect(lambda m: self.window.roster_page.status.setText(f"Couldn't read: {m}"))
        self.pool.start(job)

    def _roster_detected(self, detected):
        if not detected:
            self.window.roster_page.status.setText(
                "No names found. Open a race's Score Info in the game first.")
            return
        self.window.roster_page.apply_detected(detected)

    # --- refresh --------------------------------------------------------------

    def refresh_match(self):
        acc = self.session.pending
        self.window.match_page.refresh(self.settings, acc, busy=self.busy > 0, last_saved=self.last_saved)
        found, total = len(acc.final_scores()), len(self.settings.roster)
        in_progress = bool(found or acc.unnamed)
        self.window.setWindowTitle(f"{APP_NAME} · {found}/{total}" if in_progress else APP_NAME)
        hotkey = self.settings.capture_hotkey.upper() if self._hotkey_registered else "no hotkey"
        clip = "on" if self.watch_clipboard else "off"
        self.window.status.setText(f"Capture hotkey: {hotkey}\nClipboard snips: {clip}")
        self.window.status.setToolTip(f"Data folder: {self.settings.data_dir}")

    def refresh_analysis(self):
        self.window.analysis_page.refresh(analyze(load_scores(self.settings), self.settings))

    def refresh_all(self):
        self.refresh_match()
        self.refresh_analysis()
        names = set(load_scores(self.settings)["character"].unique())
        self.window.roster_page.load(self.settings, names)

    def shutdown(self):
        """Finish reading screenshots, save an unfinished match as partial, release the hotkey."""
        if self._shut_down:
            return
        self._shut_down = True
        self.timer.stop()
        self.pool.waitForDone(10_000)
        if self.session.pending_count:
            self.session.save()
        if sys.platform == "win32" and self._hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.window.winId()), HOTKEY_ID)
            self._hotkey_registered = False


def _setup_logging(settings: Settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _make_app() -> QApplication:
    if sys.platform == "win32":
        # Show the app's own icon on the taskbar instead of Python's
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TeamTrialsScoreTracker")
        except (AttributeError, OSError):
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "icon.png")))
    app.setStyleSheet(theme.STYLESHEET)
    return app


def run() -> int:
    """Open the app. Returns the exit code."""
    app = _make_app()
    try:
        settings = load_settings()
    except SettingsError as e:
        QMessageBox.critical(None, APP_NAME,
                             f"Your settings file couldn't be read:\n\n{e}\n\n"
                             "Fix the file (or delete it to start over), then open the app again.")
        return 1
    _setup_logging(settings)
    try:
        migrated = migrate_legacy(settings)
        if migrated:
            logger.info("Migrated %d matches to %s", migrated, settings.scores_path)
    except Exception as e:  # noqa: BLE001 - shown to the user
        logger.exception("Migrating old data failed")
        QMessageBox.warning(None, APP_NAME, f"Your old match data couldn't be converted:\n\n{e}")

    if not ocr.configure(settings.tesseract_cmd):
        QMessageBox.warning(
            None, APP_NAME,
            "Tesseract OCR was not found, so screenshots can't be read yet.\n\n"
            "Install it from https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"Expected at: {settings.tesseract_cmd}\n\n"
            f"If it's installed elsewhere, set tesseract_cmd in\n{settings.settings_path}\n"
            "or add its folder to your PATH, then restart the app.\n\n"
            "You can still look at your analysis and roster.")

    tracker = TrackerApp(app, settings)
    tracker.window.show_page(0 if settings.roster else 2)
    tracker.window.show()
    return app.exec()
