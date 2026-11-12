"""
Execution repository for Phase 2 database access: execution history, change groups,
validation results, approvals, and automation settings.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import (
    ChangeGroupModel,
    ExecutionApprovalModel,
    ExecutionHistoryModel,
    RepositoryAutomationSettingsModel,
    ValidationResultModel,
)
from utils.logger import logger


class ExecutionRepository:
    """Manages Phase 2 execution history, approvals, validation records and automation settings."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    # =========================================================================
    # Repository Automation Settings
    # =========================================================================

    def get_automation_settings(self, repository_id: int) -> RepositoryAutomationSettingsModel:
        """
        Get automation settings for a repository.
        If no record exists, creates default record with Auto Commit disabled.
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM repository_automation_settings WHERE repository_id = ?",
                (repository_id,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                branches = json.loads(d.get("protected_branches") or '["main", "master"]')
                return RepositoryAutomationSettingsModel(
                    repository_id=d["repository_id"],
                    execution_mode=d["execution_mode"],
                    auto_commit_enabled=bool(d["auto_commit_enabled"]),
                    push_enabled=bool(d["push_enabled"]),
                    protected_branches=branches,
                    validation_required=bool(d["validation_required"]),
                    quiet_period_seconds=float(d["quiet_period_seconds"]),
                )

        # Default settings: Smart mode, auto_commit=False, push=False
        return self.save_automation_settings(
            RepositoryAutomationSettingsModel(
                repository_id=repository_id,
                execution_mode="smart",
                auto_commit_enabled=False,
                push_enabled=False,
                protected_branches=["main", "master"],
                validation_required=True,
                quiet_period_seconds=3.0,
            )
        )

    def save_automation_settings(
        self, settings_model: RepositoryAutomationSettingsModel
    ) -> RepositoryAutomationSettingsModel:
        branches_json = json.dumps(settings_model.protected_branches)
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO repository_automation_settings
                    (repository_id, execution_mode, auto_commit_enabled, push_enabled,
                     protected_branches, validation_required, quiet_period_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    execution_mode = excluded.execution_mode,
                    auto_commit_enabled = excluded.auto_commit_enabled,
                    push_enabled = excluded.push_enabled,
                    protected_branches = excluded.protected_branches,
                    validation_required = excluded.validation_required,
                    quiet_period_seconds = excluded.quiet_period_seconds
                """,
                (
                    settings_model.repository_id,
                    settings_model.execution_mode,
                    1 if settings_model.auto_commit_enabled else 0,
                    1 if settings_model.push_enabled else 0,
                    branches_json,
                    1 if settings_model.validation_required else 0,
                    settings_model.quiet_period_seconds,
                ),
            )
        return settings_model

    # =========================================================================
    # Execution History
    # =========================================================================

    def create_execution(
        self,
        repository_id: int,
        execution_mode: str = "smart",
        status: str = "pending",
        proposal_data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionHistoryModel:
        now = get_utc_now_iso()
        proposal_str = json.dumps(proposal_data) if proposal_data else None
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO execution_history
                    (repository_id, execution_mode, status, created_at, proposal_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (repository_id, execution_mode, status, now, proposal_str),
            )
            exec_id = cursor.lastrowid
        return ExecutionHistoryModel(
            id=exec_id,
            repository_id=repository_id,
            execution_mode=execution_mode,
            status=status,
            commit_hash=None,
            commit_message=None,
            created_at=now,
            proposal_data=proposal_str,
        )

    def get_execution(self, execution_id: int) -> Optional[ExecutionHistoryModel]:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM execution_history WHERE id = ?", (execution_id,)
            )
            row = cursor.fetchone()
            if row:
                return ExecutionHistoryModel(**dict(row))
        return None

    def list_executions(
        self, repository_id: int, limit: int = 50
    ) -> List[ExecutionHistoryModel]:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM execution_history
                WHERE repository_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (repository_id, limit),
            )
            rows = cursor.fetchall()
            return [ExecutionHistoryModel(**dict(r)) for r in rows]

    def update_execution(
        self,
        execution_id: int,
        status: Optional[str] = None,
        commit_hash: Optional[str] = None,
        commit_message: Optional[str] = None,
        error_summary: Optional[str] = None,
        completed_at: Optional[str] = None,
        proposal_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExecutionHistoryModel]:
        proposal_str = json.dumps(proposal_data) if proposal_data is not None else None
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE execution_history
                SET status = COALESCE(?, status),
                    commit_hash = COALESCE(?, commit_hash),
                    commit_message = COALESCE(?, commit_message),
                    error_summary = COALESCE(?, error_summary),
                    completed_at = COALESCE(?, completed_at),
                    proposal_data = COALESCE(?, proposal_data)
                WHERE id = ?
                """,
                (
                    status,
                    commit_hash,
                    commit_message,
                    error_summary,
                    completed_at,
                    proposal_str,
                    execution_id,
                ),
            )
        return self.get_execution(execution_id)

    def get_active_proposal(self, repository_id: int) -> Optional[ExecutionHistoryModel]:
        """Find the latest execution still awaiting approval or pending execution."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM execution_history
                WHERE repository_id = ? AND status IN ('awaiting_approval', 'approved')
                ORDER BY id DESC LIMIT 1
                """,
                (repository_id,),
            )
            row = cursor.fetchone()
            if row:
                return ExecutionHistoryModel(**dict(row))
        return None

    # =========================================================================
    # Change Groups
    # =========================================================================

    def save_change_groups(
        self, execution_id: int, groups: List[Dict[str, Any]]
    ) -> List[ChangeGroupModel]:
        results = []
        with self.db.get_cursor() as cursor:
            # Delete existing groups if any
            cursor.execute("DELETE FROM change_groups WHERE execution_id = ?", (execution_id,))
            for g in groups:
                file_list_json = json.dumps(g.get("file_list", []))
                cursor.execute(
                    """
                    INSERT INTO change_groups (execution_id, group_name, explanation, confidence, file_list)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        execution_id,
                        g.get("group_name", "General"),
                        g.get("explanation", ""),
                        float(g.get("confidence", 1.0)),
                        file_list_json,
                    ),
                )
                results.append(
                    ChangeGroupModel(
                        id=cursor.lastrowid,
                        execution_id=execution_id,
                        group_name=g.get("group_name", "General"),
                        explanation=g.get("explanation"),
                        confidence=float(g.get("confidence", 1.0)),
                        file_list=g.get("file_list", []),
                    )
                )
        return results

    def get_change_groups(self, execution_id: int) -> List[ChangeGroupModel]:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM change_groups WHERE execution_id = ? ORDER BY id ASC",
                (execution_id,),
            )
            rows = cursor.fetchall()
            models = []
            for r in rows:
                d = dict(r)
                files = json.loads(d.get("file_list") or "[]")
                models.append(
                    ChangeGroupModel(
                        id=d["id"],
                        execution_id=d["execution_id"],
                        group_name=d["group_name"],
                        explanation=d["explanation"],
                        confidence=float(d["confidence"]),
                        file_list=files,
                    )
                )
            return models

    # =========================================================================
    # Validation Results
    # =========================================================================

    def record_validation_result(
        self,
        execution_id: int,
        validation_type: str,
        status: str,
        output_summary: Optional[str] = None,
        duration: float = 0.0,
    ) -> ValidationResultModel:
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO validation_results
                    (execution_id, validation_type, status, output_summary, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (execution_id, validation_type, status, output_summary, duration, now),
            )
            vid = cursor.lastrowid
        return ValidationResultModel(
            id=vid,
            execution_id=execution_id,
            validation_type=validation_type,
            status=status,
            output_summary=output_summary,
            duration=duration,
            created_at=now,
        )

    def get_validation_results(self, execution_id: int) -> List[ValidationResultModel]:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM validation_results WHERE execution_id = ? ORDER BY id ASC",
                (execution_id,),
            )
            rows = cursor.fetchall()
            return [ValidationResultModel(**dict(r)) for r in rows]

    # =========================================================================
    # Approvals
    # =========================================================================

    def set_approval(
        self,
        execution_id: int,
        approval_status: str,
        approved_by: str = "user",
        notes: Optional[str] = None,
    ) -> ExecutionApprovalModel:
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO execution_approvals
                    (execution_id, approval_status, approved_at, approved_by, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (execution_id, approval_status, now, approved_by, notes),
            )
            aid = cursor.lastrowid
        return ExecutionApprovalModel(
            id=aid,
            execution_id=execution_id,
            approval_status=approval_status,
            approved_at=now,
            approved_by=approved_by,
            notes=notes,
        )

    def get_approval(self, execution_id: int) -> Optional[ExecutionApprovalModel]:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM execution_approvals WHERE execution_id = ? ORDER BY id DESC LIMIT 1",
                (execution_id,),
            )
            row = cursor.fetchone()
            if row:
                return ExecutionApprovalModel(**dict(row))
        return None

