"""
Weekly Random Scheduler for AutoGit AI (Phase 3).
Schedules autonomous development sessions on 5 randomly selected days each week.
Persists schedules in SQLite and preserves them across application restarts.
"""

from datetime import date, datetime, timedelta, timezone
import random
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from config.settings import settings
from database.db import DatabaseManager, db as default_db
from database.models import ScheduledSessionModel, WeeklyScheduleModel
from database.schedule_repository import ScheduleRepository
from utils.logger import logger


# Predefined candidate time windows for scheduled development sessions
STANDARD_TIME_WINDOWS = [
    "09:00-11:00",
    "11:00-13:00",
    "13:00-15:00",
    "15:00-17:00",
    "17:00-19:00",
    "19:00-21:00",
    "21:00-23:00",
]


class WeeklyScheduler:
    """
    Manages the 5-day random weekly development schedule.
    Selects 5 unique days at random (including weekends with equal chance).
    Persists schedules in SQLite and preserves them across application restarts.
    """

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        schedule_repo: Optional[ScheduleRepository] = None,
        tz_name: Optional[str] = None,
    ):
        self.db = database or default_db
        self.schedule_repo = schedule_repo or ScheduleRepository(self.db)
        self.tz_name = tz_name or settings.SCHEDULER_TIMEZONE
        try:
            self.tz = ZoneInfo(self.tz_name)
        except Exception:
            logger.warning(f"Invalid timezone '{self.tz_name}', falling back to UTC")
            self.tz = timezone.utc
            self.tz_name = "UTC"

    def get_current_time(self) -> datetime:
        """Return the current datetime localized to the scheduler timezone."""
        return datetime.now(self.tz)

    def get_week_identifier(self, dt: Optional[datetime] = None) -> Tuple[str, int, int]:
        """
        Return (week_identifier, year, week_number) based on ISO calendar.
        Example: ('2026-W46', 2026, 46)
        """
        ref_dt = dt or self.get_current_time()
        iso_year, iso_week, _ = ref_dt.isocalendar()
        identifier = f"{iso_year}-W{iso_week:02d}"
        return identifier, iso_year, iso_week

    def get_or_create_current_week_schedule(
        self, force_regenerate: bool = False
    ) -> Tuple[WeeklyScheduleModel, List[ScheduledSessionModel]]:
        """
        Get schedule for current ISO week.
        If schedule already exists in database, returns it without regenerating
        (ensures persistence across restarts).
        If missing or force_regenerate is True, generates a new 5-day schedule.
        """
        week_id, year, week_num = self.get_week_identifier()

        if not force_regenerate:
            existing = self.schedule_repo.get_weekly_schedule_by_identifier(week_id)
            if existing:
                sessions = self.schedule_repo.get_sessions_for_schedule(existing.id)
                logger.info(
                    f"Loaded existing weekly schedule {week_id} from database "
                    f"({len(sessions)} scheduled sessions)."
                )
                return existing, sessions

        logger.info(f"Generating new weekly schedule for {week_id} in timezone {self.tz_name}")
        return self.generate_schedule_for_week(year, week_num)

    def generate_schedule_for_week(
        self, year: int, week_number: int
    ) -> Tuple[WeeklyScheduleModel, List[ScheduledSessionModel]]:
        """
        Generate a schedule for the specified ISO week with exactly 5 unique random days.
        Days 0 to 6 (Monday to Sunday) all have equal probability.
        """
        week_id = f"{year}-W{week_number:02d}"

        # Select exactly 5 distinct days out of 7 (Monday=0 to Sunday=6)
        selected_days = sorted(random.sample(range(7), settings.SCHEDULER_DAYS_PER_WEEK))

        schedule_model = WeeklyScheduleModel(
            id=None,
            week_identifier=week_id,
            year=year,
            week_number=week_number,
            timezone=self.tz_name,
            is_active=self.is_active(),
        )

        sessions: List[ScheduledSessionModel] = []
        for day_idx in selected_days:
            # fromisocalendar: day 1 is Monday, day 7 is Sunday
            cal_date = date.fromisocalendar(year, week_number, day_idx + 1)
            time_slot = random.choice(STANDARD_TIME_WINDOWS)
            sessions.append(
                ScheduledSessionModel(
                    id=None,
                    schedule_id=0,  # Will be populated during DB insertion
                    scheduled_date=cal_date.isoformat(),
                    day_of_week=day_idx,
                    time_window=time_slot,
                    status="scheduled",
                    notes=f"Auto-generated session for {cal_date.strftime('%A')}",
                )
            )

        saved_schedule, saved_sessions = self.schedule_repo.create_weekly_schedule(
            schedule_model, sessions
        )
        logger.info(
            f"Created weekly schedule {week_id}: "
            f"{[s.scheduled_date for s in saved_sessions]}"
        )
        return saved_schedule, saved_sessions

    def is_today_scheduled(
        self, target_date: Optional[date] = None
    ) -> Tuple[bool, Optional[ScheduledSessionModel]]:
        """
        Check if today (or specified date) has a scheduled development session.
        """
        d = target_date or self.get_current_time().date()
        date_str = d.isoformat()

        # Ensure current week schedule is loaded/created
        self.get_or_create_current_week_schedule()

        session = self.schedule_repo.get_session_by_date(date_str)
        if session:
            return True, session
        return False, None

    def pause(self) -> None:
        """Pause the weekly scheduler."""
        self.schedule_repo.set_scheduler_active(False)
        logger.info("Autonomous development scheduler paused.")

    def resume(self) -> None:
        """Resume the weekly scheduler."""
        self.schedule_repo.set_scheduler_active(True)
        logger.info("Autonomous development scheduler resumed.")

    def is_active(self) -> bool:
        """Check if scheduler is currently active."""
        return self.schedule_repo.is_scheduler_active()

    def mark_session_completed(
        self, session_id: int, executed_at: Optional[str] = None, notes: Optional[str] = None
    ) -> bool:
        """Mark a scheduled session as completed."""
        return self.schedule_repo.update_session_status(
            session_id=session_id,
            status="completed",
            executed_at=executed_at or datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )

    def mark_session_missed(self, session_id: int, notes: Optional[str] = None) -> bool:
        """Mark a scheduled session as missed."""
        return self.schedule_repo.update_session_status(
            session_id=session_id,
            status="missed",
            notes=notes or "System offline during scheduled window",
        )

    def get_pending_catch_up_session(self) -> Optional[ScheduledSessionModel]:
        """
        Evaluate if there are missed sessions for the current week.
        According to catch-up policy: return at most one session to catch up,
        marking older missed sessions as 'missed' to avoid aggressive burst execution.
        """
        today_str = self.get_current_time().date().isoformat()
        schedule, sessions = self.get_or_create_current_week_schedule()

        missed = [s for s in sessions if s.status == "scheduled" and s.scheduled_date < today_str]
        if not missed:
            return None

        if settings.SCHEDULER_CATCH_UP_POLICY == "single":
            # Pick the most recent missed session to run, mark all older ones as missed
            catch_up = missed[-1]
            for s in missed[:-1]:
                self.mark_session_missed(s.id, notes="Skipped older missed session (catch-up policy: single)")
            logger.info(f"Identified single catch-up session: {catch_up.scheduled_date}")
            return catch_up
        elif settings.SCHEDULER_CATCH_UP_POLICY == "skip":
            for s in missed:
                self.mark_session_missed(s.id, notes="Marked missed (catch-up policy: skip)")
            return None

        return None

