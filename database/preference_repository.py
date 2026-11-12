"""
Preference repository for Phase 4 database access: user dashboard preferences.
"""

from typing import Dict, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import DashboardPreferenceModel


class PreferenceRepository:
    """Manages key-value dashboard preferences in SQLite."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch preference value by key."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT preference_value FROM dashboard_preferences WHERE preference_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row:
                return row["preference_value"]
        return default

    def set_preference(self, key: str, value: str) -> None:
        """Store or update preference value."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dashboard_preferences (preference_key, preference_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(preference_key) DO UPDATE SET
                    preference_value=excluded.preference_value,
                    updated_at=excluded.updated_at
                """,
                (key, value, now),
            )

    def get_all_preferences(self) -> Dict[str, str]:
        """Retrieve all preferences as a dict."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT preference_key, preference_value FROM dashboard_preferences")
            rows = cursor.fetchall()
            return {r["preference_key"]: r["preference_value"] for r in rows}

