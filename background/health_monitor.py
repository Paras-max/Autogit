"""
Health Monitor for AutoGit AI (Phase 4).
Performs ongoing health checks: database connectivity, scheduler status,
active file monitors, process locks, and service heartbeat.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from monitoring.file_monitor import file_monitor
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger


class HealthMonitor:
    """Monitors system health, process liveliness, and records heartbeats in SQLite."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        scheduler: Optional[WeeklyScheduler] = None,
    ):
        self.db = database or default_db
        self.scheduler = scheduler or WeeklyScheduler(self.db)
        self.start_time = time.time()

    def record_heartbeat(self, service_name: str = "autogit-background", status: str = "running") -> None:
        """Update service heartbeat in application_service_status table."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO application_service_status (service_name, status, last_heartbeat, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(service_name) DO UPDATE SET
                    status=excluded.status,
                    last_heartbeat=excluded.last_heartbeat,
                    updated_at=excluded.updated_at
                """,
                (service_name, status, now, now),
            )

    def check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health inspection."""
        now = get_utc_now_iso()
        uptime_seconds = int(time.time() - self.start_time)

        # 1. Database check
        db_ok = False
        db_error = None
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
        except Exception as e:
            db_error = str(e)

        # 2. Scheduler check
        scheduler_active = self.scheduler.is_active()

        # 3. Active file monitors
        active_monitors = len(file_monitor._observers)

        # 4. Service status
        overall_status = "healthy" if db_ok else "unhealthy"
        self.record_heartbeat(status=overall_status)

        return {
            "status": overall_status,
            "timestamp": now,
            "uptime_seconds": uptime_seconds,
            "database": {
                "connected": db_ok,
                "error": db_error,
            },
            "scheduler": {
                "active": scheduler_active,
                "timezone": self.scheduler.tz_name,
            },
            "monitoring": {
                "active_observers": active_monitors,
            },
            "pid": os.getpid(),
        }
