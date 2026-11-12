"""Desktop notifications.

Uses the tray icon's native notification when the tray app is running,
otherwise falls back to a Windows toast shown through PowerShell.
"""

import logging
import subprocess
import sys
import threading
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

_tray_icon = None


def set_tray_icon(icon):
    """Route notifications through a running pystray icon (None to unset)."""
    global _tray_icon
    _tray_icon = icon


def _ps_quote(text):
    """Quote for a PowerShell single-quoted string (no variable expansion)."""
    return "'" + text.replace("'", "''") + "'"


def _powershell_toast(title, message):
    xml = (
        '<toast><visual><binding template="ToastText02">'
        f'<text id="1">{escape(title)}</text><text id="2">{escape(message)}</text>'
        "</binding></visual></toast>"
    )
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml({_ps_quote(xml)})
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Score Tracker').Show($toast)
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("Toast failed: %s", result.stderr.strip())
    except Exception as e:
        logger.warning("Toast exception: %s", e)


def notify(title, message):
    """Show a notification without blocking the caller."""
    logger.info("Notify: %s - %s", title, message.replace("\n", " | "))
    icon = _tray_icon
    if icon is not None:
        try:
            icon.notify(message, title)
            return
        except Exception as e:
            logger.warning("Tray notification failed, falling back to toast: %s", e)
    if sys.platform == "win32":
        threading.Thread(target=_powershell_toast, args=(title, message), daemon=True).start()


def notify_error(message):
    notify("Score Tracker", message)
