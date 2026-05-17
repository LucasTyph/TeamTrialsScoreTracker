"""System tray application for background score tracking."""
import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from io import BytesIO

import pystray
from PIL import Image, ImageDraw

import config
from clipboard_monitor import ClipboardMonitor
from notifications import notify
from analysis import format_report
from storage import load_data

logger = logging.getLogger("tray_app")


def _setup_logging():
    """Configure logging to both file and console."""
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray.log")

    # Root logger for all modules
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

    # File handler
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def _icon_image():
    """Create a simple icon in memory."""
    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#4CAF50")
    draw.text((14, 14), "S", fill="white")
    return img


def _create_menu(tray, monitor):
    """Create the tray icon menu."""
    return pystray.Menu(
        pystray.MenuItem("Analyze", lambda: _cmd_analyze()),
        pystray.MenuItem("View Last Match", lambda: _cmd_last_match()),
        pystray.MenuItem("Pause Monitoring", lambda: _cmd_toggle(monitor, tray), checked=lambda item: monitor.is_running),
        pystray.MenuItem("Exit", lambda: _cmd_exit(tray)),
    )


def _cmd_analyze():
    """Show analysis in a Tkinter popup window."""
    df = load_data()
    if df.empty:
        notify("Score Tracker", "No match data found yet.")
        return

    report = format_report(df, k=config.ADJUSTED_SCORE_K)
    _show_report_window(report)


def _show_report_window(report_text):
    """Open a Tkinter window with the full analysis report in a separate thread."""

    def _run_window():
        root = tk.Tk()
        root.title("Score Tracker — Analysis")
        root.geometry("950x650")
        root.minsize(600, 400)
        root.resizable(True, True)

        # Main frame
        frame = ttk.Frame(root, padding="8")
        frame.pack(fill=tk.BOTH, expand=True)

        # Report text area
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

        # Button frame
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        def copy_all():
            root.clipboard_clear()
            root.clipboard_append(report_text)
            root.update()
            messagebox.showinfo("Copied", "Report copied to clipboard", parent=root)

        ttk.Button(btn_frame, text="Copy All", command=copy_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Close", command=root.destroy).pack(side=tk.RIGHT, padx=4)

        # Bring to front and focus
        root.lift()
        root.attributes("-topmost", True)
        root.after_idle(root.attributes, "-topmost", False)
        root.focus_force()
        root.mainloop()

    # Run Tkinter in its own thread to avoid blocking the tray icon
    threading.Thread(target=_run_window, daemon=True).start()


def _cmd_last_match():
    """Show the most recent match in a Tkinter popup."""
    df = load_data()
    if df.empty:
        notify("Score Tracker", "No match data found yet.")
        return

    last = df.iloc[-1]
    ts = last.get("timestamp", "Unknown")
    score_cols = [c for c in df.columns if c != "timestamp"]
    total = last[score_cols].sum()

    lines = [f"Last Match: {ts}", f"Total Score: {total:,}", "", "Characters:"]
    for col in score_cols:
        val = last[col]
        if not str(val) == "nan":
            lines.append(f"  {col:20s} {int(val):>8,}")

    _show_report_window("\n".join(lines))


def _cmd_toggle(monitor, tray):
    """Toggle monitoring on/off."""
    if monitor.is_running:
        monitor.stop()
        notify("Score Tracker", "Monitoring paused")
    else:
        monitor.start()
        notify("Score Tracker", "Monitoring resumed")


def _cmd_exit(tray):
    """Exit the tray app."""
    tray.stop()


def run():
    """Start the system tray application."""
    _setup_logging()
    logger.info("Tray app starting")

    icon = _icon_image()
    monitor = ClipboardMonitor(
        on_match_complete=_on_match_complete,
        on_error=lambda msg: notify("Error", msg),
    )
    monitor.start()
    notify("Score Tracker", "Monitoring started. Take screenshots with Win+Shift+S")

    tray = pystray.Icon("score_tracker", icon, "Score Tracker")
    tray.menu = _create_menu(tray, monitor)
    logger.info("Tray icon created, entering main loop")
    tray.run()


def _on_match_complete(scores, total):
    """Save completed match to CSV and show notification."""
    from storage import append_match
    row = append_match(scores)
    ts = row.get("timestamp", "Unknown")
    notify("Match Saved", f"{ts}\nTotal: {total:,}")
    logger.info("Match saved: %s total=%d", ts, total)


if __name__ == "__main__":
    run()
