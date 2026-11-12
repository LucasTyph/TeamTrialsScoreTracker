"""System tray application for background score tracking."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from . import notifications
from .analysis import format_report
from .clipboard_monitor import ClipboardMonitor
from .config import ASSETS_DIR, Settings
from .notifications import notify
from .storage import append_match, last_match, load_scores

logger = logging.getLogger(__name__)


def _setup_logging(settings: Settings):
    """Log to data/tray.log and the console."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    for handler in (logging.FileHandler(settings.log_path, encoding="utf-8"),
                    logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def _icon_image():
    """Load custom icon from assets/, fallback to generated icon."""
    icon_path = ASSETS_DIR / "icon.png"
    if icon_path.exists():
        return Image.open(icon_path).convert("RGBA").resize((64, 64), Image.LANCZOS)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#4CAF50")
    draw.text((14, 14), "S", fill="white")
    return img


class TkThread:
    """Owns the single Tk interpreter. Tk is not thread-safe, so every window
    is created on this thread; other threads queue requests."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tk")
        self._thread.start()

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.after(100, self._poll)
        self._root.mainloop()

    def _poll(self):
        try:
            while True:
                self._queue.get_nowait()(self._root)
        except queue.Empty:
            pass
        except Exception:
            logger.exception("UI error")
        self._root.after(100, self._poll)

    def show_text(self, title, text):
        self._queue.put(lambda root: _open_text_window(root, title, text))

    def stop(self):
        self._queue.put(lambda root: root.quit())


def _open_text_window(root, title, report_text):
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("950x650")
    win.minsize(600, 400)

    frame = ttk.Frame(win, padding="8")
    frame.pack(fill=tk.BOTH, expand=True)

    text = tk.Text(frame, wrap=tk.NONE, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
    text.insert("1.0", report_text)
    text.config(state=tk.DISABLED)
    scrollbar_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
    scrollbar_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=text.xview)
    text.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
    text.grid(row=0, column=0, sticky="nsew")
    scrollbar_y.grid(row=0, column=1, sticky="ns")
    scrollbar_x.grid(row=1, column=0, sticky="ew")
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    btn_frame = ttk.Frame(win)
    btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

    def copy_all():
        win.clipboard_clear()
        win.clipboard_append(report_text)
        messagebox.showinfo("Copied", "Report copied to clipboard", parent=win)

    ttk.Button(btn_frame, text="Copy All", command=copy_all).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Close", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    win.lift()
    win.attributes("-topmost", True)
    win.after_idle(win.attributes, "-topmost", False)
    win.focus_force()


def last_match_text(scores, roster) -> str | None:
    match = last_match(scores)
    if match.empty:
        return None
    ts = match["timestamp"].iloc[0]
    total = int(match["score"].sum())
    by_name = dict(zip(match["character"], match["score"]))
    lines = [f"Last Match: {ts}", f"Total Score: {total:,}  ({len(by_name)} characters)", "", "Characters:"]
    ordered = [n for n in roster if n in by_name] + sorted(n for n in by_name if n not in roster)
    for name in ordered:
        lines.append(f"  {name:20s} {int(by_name[name]):>8,}")
    return "\n".join(lines)


class TrayApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ui = TkThread()
        self.monitor = ClipboardMonitor(
            settings,
            on_match=self._save_match,
            on_state_change=self._refresh_menu,
            on_error=lambda msg: notify("Error", msg),
        )
        self.icon = pystray.Icon("score_tracker", _icon_image(), "Score Tracker", menu=self._menu())

    def _menu(self):
        total = len(self.settings.roster)
        has_pending = lambda item: self.monitor.pending_count > 0  # noqa: E731
        return pystray.Menu(
            pystray.MenuItem("Analyze", self._cmd_analyze, default=True),
            pystray.MenuItem("View Last Match", self._cmd_last_match),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Save Partial Match ({self.monitor.pending_count}/{total})",
                             self._cmd_save_partial, enabled=has_pending),
            pystray.MenuItem("Discard Pending Match", self._cmd_discard, enabled=has_pending),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause Monitoring", self._cmd_toggle,
                             checked=lambda item: not self.monitor.is_running),
            pystray.MenuItem("Exit", self._cmd_exit),
        )

    def _refresh_menu(self):
        try:
            self.icon.update_menu()
        except Exception:
            logger.debug("Menu refresh failed", exc_info=True)

    # --- menu commands ---------------------------------------------------

    def _cmd_analyze(self):
        report = format_report(load_scores(self.settings), self.settings.roster,
                               k=self.settings.adjusted_score_k)
        self.ui.show_text("Score Tracker — Analysis", report)

    def _cmd_last_match(self):
        text = last_match_text(load_scores(self.settings), self.settings.roster)
        if text is None:
            notify("Score Tracker", "No match data found yet.")
        else:
            self.ui.show_text("Score Tracker — Last Match", text)

    def _cmd_save_partial(self):
        count = self.monitor.save_partial()
        if not count:
            notify("Score Tracker", "No pending scores to save.")

    def _cmd_discard(self):
        count = self.monitor.discard_pending()
        notify("Score Tracker", f"Discarded {count} pending score(s).")

    def _cmd_toggle(self):
        if self.monitor.is_running:
            self.monitor.stop()
            notify("Score Tracker", "Monitoring paused")
        else:
            self.monitor.start()
            notify("Score Tracker", "Monitoring resumed")
        self._refresh_menu()

    def _cmd_exit(self):
        self.monitor.stop()
        if self.monitor.pending_count:
            self.monitor.save_partial()
        self.ui.stop()
        self.icon.stop()

    # --- callbacks -------------------------------------------------------

    def _save_match(self, scores, complete, inferred):
        match_id, ts = append_match(scores, self.settings)
        total = sum(scores.values())
        status = "Match saved" if complete else "Partial match saved"
        detail = f"{ts}\n{len(scores)}/{len(self.settings.roster)} characters, total {total:,}"
        if inferred:
            detail += f"\n{inferred[0]}'s name was unreadable; matched by elimination ({inferred[1]:,})"
        notify(status, detail)
        logger.info("%s: id=%d %s total=%d inferred=%s", status, match_id, ts, total, inferred)

    def run(self):
        def setup(icon):
            icon.visible = True
            notifications.set_tray_icon(icon)
            self.monitor.start()
            notify("Score Tracker", "Monitoring started. Take screenshots with Win+Shift+S")

        logger.info("Tray app starting (data: %s)", self.settings.data_dir)
        self.icon.run(setup=setup)
        notifications.set_tray_icon(None)


def run(settings: Settings):
    """Start the system tray application."""
    _setup_logging(settings)
    TrayApp(settings).run()
