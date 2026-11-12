"""
Schedule repository for Phase 3 database access: weekly schedules and scheduled sessions.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import ScheduledSessionModel, WeeklyScheduleModel
from utils.logger import logger


class ScheduleRepository:
    """Manages weekly schedules and scheduled sessions in SQLite database."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def get_weekly_schedule_by_identifier(
        self, week_identifier: str
    ) -> Optional[WeeklyScheduleModel]:
        """Fetch weekly schedule by week identifier (e.g. '2026-W46')."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM weekly_schedules WHERE week_identifier = ?",
                (week_identifier,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return WeeklyScheduleModel(
                    id=d["id"],
                    week_identifier=d["week_identifier"],
                    year=d["year"],
                    week_number=d["week_number"],
                    timezone=d["timezone"],
                    is_active=bool(d["is_active"]),
                    created_at=d["created_at"],
                )
        return None

    def get_sessions_for_schedule(self, schedule_id: int) -> List[ScheduledSessionModel]:
        """Fetch all sessions belonging to a schedule."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM scheduled_sessions WHERE schedule_id = ? ORDER BY scheduled_date ASC",
                (schedule_id,),
            )
            rows = cursor.fetchall()
            return [
                ScheduledSessionModel(
                    id=r["id"],
                    schedule_id=r["schedule_id"],
                    scheduled_date=r["scheduled_date"],
                    day_of_week=r["day_of_week"],
                    time_window=r["time_window"],
                    status=r["status"],
                    executed_at=r["executed_at"],
                    notes=r["notes"],
                )
                for r in rows
            ]

    def create_weekly_schedule(
        self,
        schedule: WeeklyScheduleModel,
        sessions: List[ScheduledSessionModel],
    ) -> Tuple[WeeklyScheduleModel, List[ScheduledSessionModel]]:
        """Store a new weekly schedule and its scheduled sessions."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            # Clean up any existing schedule for this week if replacing/regenerating
            cursor.execute(
                "DELETE FROM weekly_schedules WHERE week_identifier = ?",
                (schedule.week_identifier,),
            )
            cursor.execute(
                """
                INSERT INTO weekly_schedules (week_identifier, year, week_number, timezone, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.week_identifier,
                    schedule.year,
                    schedule.week_number,
                    schedule.timezone,
                    int(schedule.is_active),
                    now,
                ),
            )
            schedule_id = cursor.lastrowid
            schedule.id = schedule_id
            schedule.created_at = now

            saved_sessions: List[ScheduledSessionModel] = []
            for s in sessions:
                cursor.execute(
                    """
                    INSERT INTO scheduled_sessions (schedule_id, scheduled_date, day_of_week, time_window, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule_id,
                        s.scheduled_date,
                        s.day_of_week,
                        s.time_window,
                        s.status,
                        s.notes,
                    ),
                )
                s.id = cursor.lastrowid
                s.schedule_id = schedule_id
                saved_sessions.append(s)

        return schedule, saved_sessions

    def get_session_by_date(self, scheduled_date: str) -> Optional[ScheduledSessionModel]:
        """Find a scheduled session by date string (YYYY-MM-DD)."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM scheduled_sessions WHERE scheduled_date = ?",
                (scheduled_date,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return ScheduledSessionModel(
                    id=d["id"],
                    schedule_id=d["schedule_id"],
                    scheduled_date=d["scheduled_date"],
                    day_of_week=d["day_of_week"],
                    time_window=d["time_window"],
                    status=d["status"],
                    executed_at=d["executed_at"],
                    notes=d["notes"],
                )
        return None

    def update_session_status(
        self,
        session_id: int,
        status: str,
        executed_at: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update status and metadata for a scheduled session."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE scheduled_sessions
                SET status = ?,
                    executed_at = COALESCE(?, executed_at),
                    notes = COALESCE(?, notes)
                WHERE id = ?
                """,
                (status, executed_at, notes, session_id),
            )
            return cursor.rowcount > 0

    def set_scheduler_active(self, is_active: bool) -> None:
        """Set active/paused state for current active schedules and application setting."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE weekly_schedules SET is_active = ?",
                (int(is_active),),
            )
            cursor.execute(
                """
                INSERT INTO application_settings (setting_key, setting_value, updated_at)
                VALUES ('scheduler_active', ?, datetime('now'))
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value=excluded.setting_value,
                    updated_at=excluded.updated_at
                """,
                (str(is_active).lower(),),
            )

    def is_scheduler_active(self) -> bool:
        """Check if scheduler is globally active (default True)."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT setting_value FROM application_settings WHERE setting_key = 'scheduler_active'"
            )
            row = cursor.fetchone()
            if row:
                return row["setting_value"].lower() in ("true", "1", "yes")
        return True

    def list_all_schedules(self, limit: int = 20) -> List[WeeklyScheduleModel]:
        """List past and current weekly schedules."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM weekly_schedules ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                WeeklyScheduleModel(
                    id=r["id"],
                    week_identifier=r["week_identifier"],
                    year=r["year"],
                    week_number=r["week_number"],
                    timezone=r["timezone"],
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

