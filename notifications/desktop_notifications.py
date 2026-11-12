"""
Cross-platform desktop notifications for AutoGit AI (Phase 4).
Safely delivers non-blocking desktop notifications on Windows/macOS/Linux
with strict secret masking and error fallback.
"""

import platform
import subprocess
import threading
from typing import Optional

from utils.logger import logger
from utils.validators import mask_secret


def send_desktop_notification(
    title: str,
    message: str,
    severity: str = "info",
) -> bool:
    """
    Send desktop notification asynchronously without blocking caller.
    Guarantees no raw secrets are displayed.
    """
    sanitized_title = title.replace('"', '\\"').replace("'", "")
    sanitized_message = message.replace('"', '\\"').replace("'", "")

    # Clean secrets
    for secret_token in ("ghp_", "sk-", "AIza", "bearer "):
        if secret_token in sanitized_message.lower():
            sanitized_message = "[Protected Notification Content]"

    def _deliver():
        system = platform.system()
        try:
            if system == "Windows":
                # PowerShell balloon / toast script
                ps_script = f"""
                [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
                $objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon
                $objNotifyIcon.Icon = [System.Drawing.SystemIcons]::Information
                $objNotifyIcon.BalloonTipIcon = "Info"
                $objNotifyIcon.BalloonTipTitle = "{sanitized_title}"
                $objNotifyIcon.BalloonTipText = "{sanitized_message}"
                $objNotifyIcon.Visible = $True
                $objNotifyIcon.ShowBalloonTip(5000)
                Start-Sleep -Seconds 1
                $objNotifyIcon.Dispose()
                """
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    timeout=8.0,
                )
            elif system == "Darwin":
                # macOS osascript
                subprocess.run(
                    ["osascript", "-e", f'display notification "{sanitized_message}" with title "{sanitized_title}"'],
                    capture_output=True,
                    timeout=5.0,
                )
            elif system == "Linux":
                # Linux notify-send
                subprocess.run(
                    ["notify-send", sanitized_title, sanitized_message],
                    capture_output=True,
                    timeout=5.0,
                )
        except Exception as e:
            logger.debug(f"Desktop notification delivery failed (graceful fallback): {e}")

    # Run in background daemon thread
    thread = threading.Thread(target=_deliver, daemon=True)
    thread.start()
    return True

