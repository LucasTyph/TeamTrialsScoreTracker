"""Windows toast notifications using PowerShell."""
import subprocess
import threading
import logging

logger = logging.getLogger("notifications")


def _toast(title, message, duration=5):
    """Show a Windows toast notification via PowerShell."""
    # Escape special characters in title and message
    title = title.replace('"', '`"').replace("'", "''")
    message = message.replace('"', '`"').replace("'", "''")

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
    <toast>
        <visual>
            <binding template="ToastText02">
                <text id="1">{title}</text>
                <text id="2">{message}</text>
            </binding>
        </visual>
    </toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Score Tracker")
    $notifier.Show($toast)
    """
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("Toast failed: %s", result.stderr.strip())
    except Exception as e:
        logger.warning("Toast exception: %s", str(e))


def notify(title, message, duration=5):
    """Thread-safe toast notification."""
    threading.Thread(target=_toast, args=(title, message, duration), daemon=True).start()


def notify_score(character, score):
    """Toast for a single character score."""
    notify(character, f"Score: {score:,}")


def notify_match_complete(scores, total):
    """Toast for a completed match."""
    count = len(scores)
    notify(
        "Match Complete",
        f"{count} characters recorded\nTotal: {total:,}",
    )


def notify_error(message):
    """Toast for errors."""
    notify("Score Tracker", message)
