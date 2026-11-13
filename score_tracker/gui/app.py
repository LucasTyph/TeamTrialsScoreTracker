"""The desktop app: main window, capture hotkey and clipboard watching.

``run()`` is the program's entry point (``python -m score_tracker``).
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import sys
import threading
from dataclasses import replace
from datetime import datetime
from difflib import get_close_matches

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QInputDialog,
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
from ..flagged import flagged_dir, save_flagged
from ..lineups import Roster, apply_lineup, load_roster, save_roster
from ..pipeline import UNNAMED, detect_roster
from ..session import MatchSession
from ..storage import append_match, delete_match, load_scores, migrate_legacy, move_match
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


def wrong_lineup_names(roster: Roster, settings: Settings, result) -> dict:
    """Unreadable rows whose text matches a racer of another lineup: name -> lineup name."""
    here = set(settings.roster)
    elsewhere = {}
    for l in roster.lineups:
        if l.id == roster.active:
            continue
        for name in roster.teams(l):
            if name not in here:
                elsewhere.setdefault(name, l.name)
    found = {}
    if not elsewhere:
        return found
    for row in result.rows:
        if row.status == UNNAMED and row.read_text:
            match = get_close_matches(row.read_text, list(elsewhere), n=1, cutoff=0.75)
            if match:
                found[match[0]] = elsewhere[match[0]]
    return found


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

    def __init__(self, app: QApplication, settings: Settings, roster: Roster | None = None):
        super().__init__()
        self.app = app
        self.roster = roster if roster is not None else load_roster(settings)
        settings = apply_lineup(settings, self.roster)
        self.settings = settings
        self.analysis_filter = ""  # lineup id, "" = all lineups
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)  # one OCR job at a time, in order
        self.busy = 0
        self.last_saved = None
        self.last_capture = None  # {"img", "result", "at", "flagged"} for the most recent screenshot
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
        mp.lineup_selected.connect(self._switch_lineup)
        mp.flag_requested.connect(self._flag_last_capture)
        rp = self.window.roster_page
        rp.saved.connect(self._apply_settings)
        rp.detect_requested.connect(self._detect_roster)
        ap = self.window.analysis_page
        ap.delete_match_requested.connect(self._delete_match)
        ap.move_match_requested.connect(self._move_match)
        ap.lineup_filter_changed.connect(self._set_analysis_filter)
        ap.use_fit_toggled.connect(self._set_use_fit)

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
        job.signals.done.connect(lambda outcome, img=img: self._processed(outcome, img))
        job.signals.failed.connect(self._failed)
        self.pool.start(job)

    def _processed(self, outcome, img=None):
        self.busy -= 1
        if img is not None:
            self.last_capture = {"img": img, "result": outcome.result, "at": datetime.now(), "flagged": False}
        if outcome.ignored:
            self.notify("No scores found", "That screenshot doesn't look like a Score Info screen.", "warning")
        else:
            self._warn_wrong_lineup(outcome.result)
            completed = any(s.complete for s in outcome.saved)
            if not completed:
                review = len(self.session.pending.needs_review)
                extra = f" · {review} row(s) to review" if review else ""
                self.notify("Screenshot read",
                            f"{outcome.new_characters} new · {outcome.found}/{outcome.total} found{extra}")
        self.refresh_match()

    def _warn_wrong_lineup(self, result):
        """Unreadable names that belong to another lineup: probably forgot to switch."""
        names = wrong_lineup_names(self.roster, self.settings, result)
        if names:
            listed = ", ".join(f"{n} (in “{l}”)" for n, l in names.items())
            active = self.roster.active_lineup
            self.notify("Wrong lineup?", f"{listed} isn't in the active lineup “{active.name}”. "
                        "Switch lineups on the Current match page.", "warning")

    def _flag_last_capture(self):
        cap = self.last_capture
        if cap is None or cap["flagged"]:
            return
        note, ok = QInputDialog.getText(self.window, "Flag last capture",
                                        "What went wrong? (optional, e.g. “missed Oguri Cap”)")
        if not ok:
            return
        try:
            path = save_flagged(cap["img"], cap["result"], self.settings, note.strip(), self.roster.active)
        except OSError as e:
            self.notify("Couldn't save the screenshot", str(e), "error")
            return
        cap["flagged"] = True
        count = len(list(flagged_dir(self.settings).glob("*.png")))
        self.notify("Capture flagged", f"Saved as {path.name} · {count} flagged so far")
        self.refresh_match()

    def _failed(self, message):
        self.busy -= 1
        self.notify("Something went wrong", message, "error")
        self.refresh_match()

    # --- saving -------------------------------------------------------------

    def _store(self, saved):
        """Called by the session (possibly on the worker thread)."""
        with self._storage_lock:
            append_match(saved.scores, self.settings, saved.distances, lineup=self.roster.active)
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
        self.refresh_all()

    def _move_match(self, match_id, lineup_id):
        with self._storage_lock:
            move_match(match_id, lineup_id, self.settings)
        lineup = self.roster.lineup(lineup_id)
        self.notify("Match moved", f"Now in the lineup “{lineup.name if lineup else lineup_id}”.")
        self.refresh_all()

    def _set_analysis_filter(self, lineup_id):
        self.analysis_filter = lineup_id or ""
        self.refresh_analysis()

    def _set_use_fit(self, on):
        settings = replace(self.settings, use_fitted_bonus=bool(on))
        save_settings(settings)
        self.settings = settings
        self.session.update_settings(settings)
        self.refresh_analysis()

    # --- settings -------------------------------------------------------------

    def _apply_settings(self, settings, roster=None):
        if roster is not None:
            save_roster(roster, settings)
            self.roster = roster
        settings = apply_lineup(settings, self.roster)
        save_settings(settings)
        hotkey_changed = settings.capture_hotkey != self.settings.capture_hotkey
        self.settings = settings
        self.session.update_settings(settings)
        if hotkey_changed:
            self._register_hotkey()
        self.refresh_all()

    def _switch_lineup(self, lineup_id):
        if lineup_id == self.roster.active or self.roster.lineup(lineup_id) is None:
            return
        roster = self.roster.copy()
        roster.active = lineup_id
        self._apply_settings(self.settings, roster)
        self.notify("Lineup switched", f"New matches go to “{roster.active_lineup.name}”.")

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
        cap = self.last_capture
        self.window.match_page.refresh(self.settings, acc, busy=self.busy > 0, last_saved=self.last_saved,
                                       roster=self.roster,
                                       last_capture=(cap["at"], cap["flagged"]) if cap else None)
        found, total = len(acc.final_scores()), len(self.settings.roster)
        in_progress = bool(found or acc.unnamed)
        self.window.setWindowTitle(f"{APP_NAME} · {found}/{total}" if in_progress else APP_NAME)
        hotkey = self.settings.capture_hotkey.upper() if self._hotkey_registered else "no hotkey"
        clip = "on" if self.watch_clipboard else "off"
        self.window.status.setText(f"Capture hotkey: {hotkey}\nClipboard snips: {clip}")
        self.window.status.setToolTip(f"Data folder: {self.settings.data_dir}")

    def match_counts(self, scores) -> dict:
        if scores.empty:
            return {}
        lineups = scores.drop_duplicates("match_id")["lineup"].map(self.roster.resolve_lineup)
        return lineups.value_counts().to_dict()

    def refresh_analysis(self, scores=None):
        scores = load_scores(self.settings) if scores is None else scores
        lineup = self.roster.lineup(self.analysis_filter) if self.analysis_filter else None
        if lineup is None:
            self.analysis_filter = ""
        analysis = analyze(scores, self.settings, self.roster, lineup)
        self.window.analysis_page.refresh(analysis, self.roster, self.analysis_filter, self.match_counts(scores),
                                          self.settings)

    def refresh_all(self):
        scores = load_scores(self.settings)
        self.refresh_match()
        self.refresh_analysis(scores)
        names = set(scores["character"].unique())
        self.window.roster_page.load(self.settings, self.roster, names, self.match_counts(scores))

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


def run(splash=None) -> int:
    """Open the app. Returns the exit code.

    ``splash`` (from launch.py) is closed once the window shows, or before
    any message box.
    """
    app = _make_app()

    def close_splash():
        if splash is not None:
            splash.close()
    try:
        settings = load_settings()
    except SettingsError as e:
        close_splash()
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
        close_splash()
        QMessageBox.warning(None, APP_NAME, f"Your old match data couldn't be converted:\n\n{e}")

    if not ocr.configure(settings.tesseract_cmd):
        close_splash()
        QMessageBox.warning(
            None, APP_NAME,
            "Tesseract OCR was not found, so screenshots can't be read yet.\n\n"
            "Install it from https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"Expected at: {settings.tesseract_cmd}\n\n"
            f"If it's installed elsewhere, set tesseract_cmd in\n{settings.settings_path}\n"
            "or add its folder to your PATH, then restart the app.\n\n"
            "You can still look at your analysis and roster.")

    try:
        roster = load_roster(settings)
    except (ValueError, KeyError, OSError) as e:
        close_splash()
        QMessageBox.critical(None, APP_NAME, f"Your lineups file couldn't be read:\n\n{e}\n\n"
                             "Fix or delete roster.json in the data folder, then open the app again.")
        return 1
    tracker = TrackerApp(app, settings, roster)
    tracker.window.show_page(0 if tracker.settings.roster else 2)
    tracker.window.show()
    if splash is not None:
        splash.finish(tracker.window)
    return app.exec()
