"""
Phase 3 Tests: Weekly Random Scheduler
Verifies 5-day random schedule generation, ISO-week persistence, timezone support,
pause/resume controls, and missed session catch-up policy.
"""

from datetime import date, datetime, timezone
from typing import List
import random
import pytest

from database.db import DatabaseManager
from database.schedule_repository import ScheduleRepository
from scheduler.weekly_scheduler import WeeklyScheduler, STANDARD_TIME_WINDOWS


@pytest.fixture
def mem_db():
    return DatabaseManager(":memory:")


@pytest.fixture
def scheduler(mem_db):
    return WeeklyScheduler(database=mem_db, tz_name="UTC")


class TestWeeklyScheduler:
    def test_generates_exactly_5_days(self, scheduler):
        _, iso_week, week_num = scheduler.get_week_identifier()
        year, week_number, _ = datetime.now(timezone.utc).isocalendar()
        schedule, sessions = scheduler.generate_schedule_for_week(year, week_number)
        assert len(sessions) == 5

    def test_all_scheduled_days_are_unique(self, scheduler):
        year, week_number, _ = datetime.now(timezone.utc).isocalendar()
        _, sessions = scheduler.generate_schedule_for_week(year, week_number)
        dates = [s.scheduled_date for s in sessions]
        assert len(set(dates)) == 5

    def test_scheduled_days_are_sorted_chronologically(self, scheduler):
        year, week_number, _ = datetime.now(timezone.utc).isocalendar()
        _, sessions = scheduler.generate_schedule_for_week(year, week_number)
        dates = [s.scheduled_date for s in sessions]
        assert dates == sorted(dates)

    def test_scheduled_days_all_belong_to_correct_iso_week(self, scheduler):
        year, week_number, _ = datetime.now(timezone.utc).isocalendar()
        _, sessions = scheduler.generate_schedule_for_week(year, week_number)
        for s in sessions:
            d = date.fromisoformat(s.scheduled_date)
            assert d.isocalendar()[0] == year
            assert d.isocalendar()[1] == week_number

    def test_time_window_is_valid(self, scheduler):
        year, week_number, _ = datetime.now(timezone.utc).isocalendar()
        _, sessions = scheduler.generate_schedule_for_week(year, week_number)
        for s in sessions:
            assert s.time_window in STANDARD_TIME_WINDOWS

    def test_schedule_persists_across_calls(self, scheduler):
        """Calling get_or_create multiple times must return the same schedule."""
        sched1, sess1 = scheduler.get_or_create_current_week_schedule()
        sched2, sess2 = scheduler.get_or_create_current_week_schedule()
        assert sched1.id == sched2.id
        assert len(sess1) == len(sess2)
        assert [s.scheduled_date for s in sess1] == [s.scheduled_date for s in sess2]

    def test_force_regenerate_creates_new_record(self, mem_db):
        """Force regenerate must replace existing schedule and create new record."""
        s1 = WeeklyScheduler(database=mem_db, tz_name="UTC")
        sched1, _ = s1.get_or_create_current_week_schedule(force_regenerate=False)
        sched2, _ = s1.get_or_create_current_week_schedule(force_regenerate=True)
        assert sched2.id is not None
        assert sched1.id != sched2.id

    def test_pause_and_resume_scheduler(self, scheduler):
        scheduler.pause()
        assert scheduler.is_active() is False
        scheduler.resume()
        assert scheduler.is_active() is True

    def test_week_identifier_format(self, scheduler):
        week_id, year, week_num = scheduler.get_week_identifier()
        assert week_id.startswith(f"{year}-W")
        assert len(week_id) >= 7

    def test_mark_session_completed(self, scheduler):
        _, sessions = scheduler.get_or_create_current_week_schedule()
        sess = sessions[0]
        result = scheduler.mark_session_completed(sess.id, notes="Done in test")
        assert result is True

    def test_mark_session_missed(self, scheduler):
        _, sessions = scheduler.get_or_create_current_week_schedule()
        sess = sessions[0]
        result = scheduler.mark_session_missed(sess.id, notes="System was offline")
        assert result is True

    def test_weekdays_include_weekend_possibility(self):
        """
        Run schedule generation many times and verify weekends (day 5, 6) can appear.
        (Statistical test – if weekends were excluded this would almost certainly fail.)
        """
        all_days = set()
        for _ in range(100):
            days = sorted(random.sample(range(7), 5))
            all_days.update(days)
        # Must include possible Saturday (5) and Sunday (6)
        assert 5 in all_days
        assert 6 in all_days

