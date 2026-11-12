"""
Application Service Orchestrator for AutoGit AI (Phase 4).
Runs all core background components: recovery pipeline, weekly scheduler runner,
file monitors, health monitor, and event dispatcher.
"""

import asyncio
from datetime import datetime, timezone
import threading
import time
from typing import Optional

from background.health_monitor import HealthMonitor
from background.recovery_manager import RecoveryManager
from background.service_manager import service_manager
from core.permission_manager import PermissionManager
from database.db import DatabaseManager, db as default_db
from monitoring.file_monitor import file_monitor
from notifications.event_dispatcher import event_dispatcher
from notifications.notification_manager import notification_manager
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger


class ApplicationService:
    """Master application service orchestrating background processes."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
    ):
        self.db = database or default_db
        self.recovery_mgr = RecoveryManager(self.db)
        self.scheduler = WeeklyScheduler(self.db)
        self.permission_mgr = PermissionManager(self.db)
        self.health_monitor = HealthMonitor(self.db, self.scheduler)
        self._is_running = False
        self._loop_thread: Optional[threading.Thread] = None

    def initialize_on_startup(self) -> None:
        """
        Run startup lifecycle hooks:
        1. Acquire process lock.
        2. Run recovery pipeline (persisted permissions, schedule, incomplete sessions).
        3. Record service heartbeat.
        """
        logger.info("Initializing AutoGit AI Application Service...")
        service_manager.acquire_lock()
        recovery_summary = self.recovery_mgr.run_recovery_pipeline()
        self.health_monitor.record_heartbeat(status="running")
        notification_manager.notify(
            notification_type="service",
            title="AutoGit AI Started",
            message=f"Application service initialized. Schedule: {recovery_summary['schedule_week']}.",
            severity="info",
            notify_desktop=False,
        )

    def start_scheduler_worker(self) -> None:
        """Starts background periodic scheduler loop (checks daily sessions & catch-ups)."""
        if self._is_running:
            return

        self._is_running = True

        def _worker():
            logger.info("Background scheduler worker thread active.")
            while self._is_running:
                try:
                    self.health_monitor.record_heartbeat(status="running")
                    if self.scheduler.is_active():
                        # Check today's schedule
                        is_today, session = self.scheduler.is_today_scheduled()
                        if is_today and session and session.status == "scheduled":
                            logger.info(f"Today is a scheduled development day (session ID: {session.id}).")
                            # Live event broadcast
                            event_dispatcher.dispatch(
                                event_type="scheduled_session_active",
                                data={"session_id": session.id, "date": session.scheduled_date},
                            )
                except Exception as e:
                    logger.error(f"Error in scheduler background loop: {e}")
                time.sleep(30.0)

        self._loop_thread = threading.Thread(target=_worker, daemon=True)
        self._loop_thread.start()

    def shutdown(self) -> None:
        """Gracefully stop background application service."""
        logger.info("Shutting down AutoGit AI Application Service...")
        self._is_running = False
        file_monitor.stop_all()
        self.health_monitor.record_heartbeat(status="stopped")
        service_manager.release_lock()
        logger.info("AutoGit AI Application Service shutdown complete.")


# Global singleton instance
application_service = ApplicationService()

