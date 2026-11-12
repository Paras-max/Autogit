"""
Background Service Manager for AutoGit AI (Phase 4).
Controls background service lifecycle: start, stop, restart, status check,
and duplicate instance prevention via process locks.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from config.settings import settings
from utils.logger import logger


LOCK_FILE = settings.BASE_DIR / ".autogit.lock"


class ServiceManager:
    """Manages starting, stopping, restarting and querying the AutoGit AI background service."""

    def __init__(self, lock_file: Optional[Path] = None):
        self.lock_file = lock_file or LOCK_FILE

    def is_running(self) -> tuple[bool, Optional[int]]:
        """
        Check if background service process is currently running.
        Returns: (is_running, pid)
        """
        if not self.lock_file.exists():
            return False, None

        try:
            pid_str = self.lock_file.read_text(encoding="utf-8").strip()
            pid = int(pid_str)
        except Exception:
            return False, None

        # Verify whether pid is alive
        if self._is_pid_alive(pid):
            return True, pid

        # Stale lock file
        self.lock_file.unlink(missing_ok=True)
        return False, None

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if process with given PID exists."""
        if os.name == "nt":
            try:
                # Windows tasklist check
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                return str(pid) in output
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

    def acquire_lock(self, pid: Optional[int] = None) -> bool:
        """Acquire process lock to prevent duplicate instances."""
        running, existing_pid = self.is_running()
        if running:
            logger.warning(f"AutoGit AI service is already running (PID: {existing_pid}).")
            return False

        target_pid = pid or os.getpid()
        try:
            self.lock_file.write_text(str(target_pid), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to acquire service lock: {e}")
            return False

    def release_lock(self) -> None:
        """Release the service process lock."""
        self.lock_file.unlink(missing_ok=True)

    def start_service(self, host: str = "127.0.0.1", port: int = 8000) -> Dict[str, Any]:
        """Start the AutoGit AI service in the background."""
        running, pid = self.is_running()
        if running:
            return {
                "success": False,
                "message": f"Service is already running (PID: {pid}).",
                "pid": pid,
            }

        python_exe = sys.executable
        main_script = str(settings.BASE_DIR / "main.py")

        cmd = [python_exe, main_script, "run", "--host", host, "--port", str(port)]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | (subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0) if os.name == "nt" else 0

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(settings.BASE_DIR),
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Write pid to lock
            self.acquire_lock(pid=proc.pid)
            logger.info(f"AutoGit AI background service started (PID: {proc.pid}) at http://{host}:{port}")
            return {
                "success": True,
                "message": f"Service started successfully at http://{host}:{port}",
                "pid": proc.pid,
            }
        except Exception as e:
            logger.error(f"Failed to spawn background service: {e}")
            return {"success": False, "error": str(e)}

    def stop_service(self) -> Dict[str, Any]:
        """Stop running background service."""
        running, pid = self.is_running()
        if not running or not pid:
            self.release_lock()
            return {"success": True, "message": "Service is not running."}

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            self.release_lock()
            logger.info(f"AutoGit AI service stopped (PID: {pid}).")
            return {"success": True, "message": f"Service stopped (PID: {pid})."}
        except Exception as e:
            logger.error(f"Error stopping service (PID: {pid}): {e}")
            self.release_lock()
            return {"success": False, "error": str(e)}

    def restart_service(self, host: str = "127.0.0.1", port: int = 8000) -> Dict[str, Any]:
        """Restart background service."""
        self.stop_service()
        time.sleep(1.0)
        return self.start_service(host=host, port=port)

    def get_status(self) -> Dict[str, Any]:
        """Query current service status."""
        running, pid = self.is_running()
        return {
            "is_running": running,
            "pid": pid,
            "lock_file": str(self.lock_file),
        }


# Type helper
from typing import Tuple
Tuple_IsRunning = Tuple[bool, Optional[int]]

# Global singleton
service_manager = ServiceManager()

