"""System tray application for background score tracking."""
import logging
import os
import sys
import threading
from io import BytesIO

import pystray
from PIL import Image, ImageDraw

import config
from clipboard_monitor import ClipboardMonitor
from notifications import notify
from analysis import full_analysis
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
    """Show analysis in a popup window."""
    df = load_data()
    if df.empty:
        notify("Score Tracker", "No match data found yet.")
        return

    results = full_analysis(df, k=config.ADJUSTED_SCORE_K)
    lines = [f"Matches recorded: {len(df)}", ""]

    col_order = ["adjusted", "avg_rank", "mean", "std", "p75", "min", "max", "matches"]
    available = [c for c in col_order if c in results.columns]

    lines.append(results[available].to_string())
    notify("Analysis", "\n".join(lines[:10]))


def _cmd_last_match():
    """Show the most recent match."""
    df = load_data()
    if df.empty:
        notify("Score Tracker", "No match data found yet.")
        return

    last = df.iloc[-1]
    ts = last.get("timestamp", "Unknown")
    score_cols = [c for c in df.columns if c != "timestamp"]
    total = last[score_cols].sum()

    lines = [f"Last match: {ts}", f"Total: {total:,}", ""]
    for col in score_cols:
        val = last[col]
        if not str(val) == "nan":
            lines.append(f"  {col}: {int(val):,}")

    notify("Last Match", "\n".join(lines[:15]))


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
