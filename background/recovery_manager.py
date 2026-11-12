"""
Recovery Manager for AutoGit AI (Phase 4).
Runs during application startup to safely recover from unexpected restarts or crashes:
- Validates persisted repository permissions.
- Loads the weekly schedule (never regenerates for current ISO week).
- Recovers pending proposals and marks interrupted development sessions as 'interrupted'.
- Restores active file monitoring for authorized repositories.
"""

from typing import Any, Dict, List, Optional

from core.permission_manager import PermissionManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from monitoring.file_monitor import file_monitor
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger


class RecoveryManager:
    """Safely restores application state after unexpected shutdown or reboot."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        permission_mgr: Optional[PermissionManager] = None,
        scheduler: Optional[WeeklyScheduler] = None,
    ):
        self.db = database or default_db
        self.permission_mgr = permission_mgr or PermissionManager(self.db)
        self.scheduler = scheduler or WeeklyScheduler(self.db)

    def run_recovery_pipeline(self) -> Dict[str, Any]:
        """
        Execute full recovery pipeline.
        Returns recovery audit summary.
        """
        logger.info("Executing AutoGit AI crash and startup recovery pipeline...")
        now = get_utc_now_iso()

        # 1. Recover Interrupted Development Sessions
        interrupted_dev_sessions = 0
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE development_sessions
                SET status = 'interrupted',
                    completed_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            interrupted_dev_sessions = cursor.rowcount

        # 2. Recover Interrupted Execution Proposals
        interrupted_executions = 0
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE execution_history
                SET status = 'interrupted',
                    error_summary = 'Process restarted during execution',
                    completed_at = ?
                WHERE status IN ('pending', 'analyzed')
                """,
                (now,),
            )
            interrupted_executions = cursor.rowcount

        # 3. Ensure Current Weekly Schedule is Loaded (Do NOT regenerate if existing)
        schedule, sessions = self.scheduler.get_or_create_current_week_schedule()

        # 4. Restore File Monitors for Authorized Repositories
        restored_monitors = []
        try:
            authorized_repos = self.permission_mgr.get_authorized_repositories("monitoring")
            for repo in authorized_repos:
                try:
                    file_monitor.start_monitoring(repo.id)
                    restored_monitors.append(repo.id)
                except Exception as e:
                    logger.warning(f"Could not restore file monitor for repo {repo.id}: {e}")
        except Exception as e:
            logger.warning(f"Failed restoring file monitors: {e}")

        summary = {
            "timestamp": now,
            "interrupted_development_sessions": interrupted_dev_sessions,
            "interrupted_executions": interrupted_executions,
            "schedule_week": schedule.week_identifier,
            "scheduled_sessions_count": len(sessions),
            "restored_monitors_count": len(restored_monitors),
            "restored_repo_ids": restored_monitors,
            "status": "clean",
        }
        logger.info(
            f"Startup recovery completed: {interrupted_dev_sessions} dev sessions & "
            f"{interrupted_executions} executions recovered; {len(restored_monitors)} monitors active."
        )
        return summary

