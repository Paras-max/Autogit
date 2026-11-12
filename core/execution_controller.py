"""
Execution Controller for AutoGit AI.
Central orchestrator managing Smart Commit and Auto Commit workflows,
proposal invalidation, execution locks, and audit trails.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from agents.change_grouping_agent import ChangeGroupingAgent
from agents.code_understanding_agent import CodeUnderstandingAgent
from agents.commit_message_agent import CommitMessageAgent
from agents.diff_analysis_agent import DiffAnalysisAgent
from agents.validation_agent import ValidationAgent
from core.git_executor import GitExecutor
from core.git_manager import GitManager
from core.staging_manager import StagingManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.execution_repository import ExecutionRepository
from database.models import ExecutionHistoryModel, RepositoryAutomationSettingsModel
from utils.logger import logger


class ExecutionController:
    """Orchestrates AI agents, validation policies, and controlled Git execution."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        exec_repo: Optional[ExecutionRepository] = None,
        diff_agent: Optional[DiffAnalysisAgent] = None,
        understanding_agent: Optional[CodeUnderstandingAgent] = None,
        grouping_agent: Optional[ChangeGroupingAgent] = None,
        message_agent: Optional[CommitMessageAgent] = None,
        validation_agent: Optional[ValidationAgent] = None,
    ):
        self.db = database or default_db
        self.exec_repo = exec_repo or ExecutionRepository(self.db)
        self.diff_agent = diff_agent or DiffAnalysisAgent()
        self.understanding_agent = understanding_agent or CodeUnderstandingAgent()
        self.grouping_agent = grouping_agent or ChangeGroupingAgent()
        self.message_agent = message_agent or CommitMessageAgent()
        self.validation_agent = validation_agent or ValidationAgent()

        # Per-repository thread execution locks
        self._locks: Dict[int, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_repo_lock(self, repo_id: int) -> threading.Lock:
        with self._global_lock:
            if repo_id not in self._locks:
                self._locks[repo_id] = threading.Lock()
            return self._locks[repo_id]

    # =========================================================================
    # Step 1: Analyze Repository and Build Proposal
    # =========================================================================

    async def analyze_and_propose(
        self,
        repository_id: int,
        user_hint: Optional[str] = None,
        execution_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs the full analysis pipeline:
        Diff -> Code Understanding -> Change Grouping -> Commit Message -> Pre-commit Validation.
        Saves proposal to database.
        """
        lock = self._get_repo_lock(repository_id)
        if not lock.acquire(blocking=False):
            return {
                "success": False,
                "error": f"Another Git automation execution is already running for repository {repository_id}.",
            }

        try:
            repo = self.db.get_repository(repository_id)
            if not repo:
                return {"success": False, "error": f"Repository ID {repository_id} not found."}

            repo_path = Path(repo.repository_path)
            if not repo_path.exists():
                return {"success": False, "error": f"Repository path does not exist: {repo_path}"}

            git_mgr = GitManager(repo_path)
            current_branch = git_mgr.get_current_branch()
            automation_settings = self.exec_repo.get_automation_settings(repository_id)
            mode = execution_mode or automation_settings.execution_mode

            # 1. Analyze Diff
            diff_result = await self.diff_agent.analyze_diff(repo_path)
            if not diff_result.files:
                return {
                    "success": False,
                    "error": "No meaningful file modifications detected in working directory.",
                }

            # 2. Understand Code
            understanding = await self.understanding_agent.understand_changes(diff_result)

            # 3. Group Changes
            grouping = await self.grouping_agent.group_changes(diff_result, understanding)
            primary_group = grouping.groups[0] if grouping.groups else None
            target_files = primary_group.file_list if primary_group else [f.file_path for f in diff_result.files]

            # 4. Generate Commit Message
            message_res = await self.message_agent.generate_commit_message(
                files=target_files,
                diff_result=diff_result,
                understanding=understanding,
                user_hint=user_hint,
            )

            # 5. Run Validations and Policies
            validation_report = self.validation_agent.run_all_validations(
                repo_path=repo_path,
                current_branch=current_branch,
                target_files=target_files,
                total_diff_chars=diff_result.total_additions + diff_result.total_deletions,
                settings=automation_settings,
            )

            # Package proposal data
            proposal_dict = {
                "repository_id": repository_id,
                "repository_name": repo.repository_name,
                "branch": current_branch,
                "diff_summary": diff_result.summary,
                "total_additions": diff_result.total_additions,
                "total_deletions": diff_result.total_deletions,
                "primary_language": understanding.primary_language,
                "logical_task": understanding.logical_task,
                "risk_level": understanding.risk_level,
                "proposed_files": target_files,
                "proposed_message": message_res.full_message,
                "commit_type": message_res.commit_type,
                "subject": message_res.subject,
                "body": message_res.body,
                "groups": [g.model_dump() for g in grouping.groups],
                "validation": validation_report,
            }

            # Save in SQLite
            execution_record = self.exec_repo.create_execution(
                repository_id=repository_id,
                execution_mode=mode,
                status="pending",
                proposal_data=proposal_dict,
            )
            exec_id = execution_record.id
            assert exec_id is not None

            # Save change groups in DB
            self.exec_repo.save_change_groups(
                exec_id, [g.model_dump() for g in grouping.groups]
            )

            # Save validation records
            for v_type, data in [
                ("secret", validation_report["secret_scan"]),
                ("test", validation_report["tests"]),
                ("lint", validation_report["lint"]),
                ("build", validation_report["build"]),
                ("policy", validation_report["policies"]),
            ]:
                st = data.get("status") or ("FAILED" if data.get("has_secrets") else "PASSED")
                dur = float(data.get("duration", 0.0))
                out = data.get("output") or (
                    f"Findings: {data.get('findings_count', 0)}" if "findings_count" in data else ""
                )
                self.exec_repo.record_validation_result(
                    execution_id=exec_id,
                    validation_type=v_type,
                    status=st,
                    output_summary=out,
                    duration=dur,
                )

            # Determine whether Auto Commit can proceed immediately
            policies = validation_report["policies"]
            is_auto_eligible = (
                mode == "auto"
                and automation_settings.auto_commit_enabled
                and policies.get("auto_commit_eligible", False)
                and validation_report["all_passed"]
            )

            if is_auto_eligible:
                logger.info(
                    f"Auto Commit policy passed for execution ID {exec_id}. Executing automatically."
                )
                commit_res = self._execute_commit_internal(
                    execution_id=exec_id,
                    repo_path=repo_path,
                    target_files=target_files,
                    commit_message=message_res.full_message,
                    settings=automation_settings,
                    approved_by="auto",
                )
                return {
                    "success": commit_res["success"],
                    "execution_id": exec_id,
                    "mode": "auto",
                    "status": "committed" if commit_res["success"] else "failed",
                    "commit_hash": commit_res.get("commit_hash"),
                    "proposal": proposal_dict,
                    "error": commit_res.get("error"),
                }
            else:
                # Mode A: Smart Commit awaiting explicit user approval
                self.exec_repo.update_execution(
                    execution_id=exec_id, status="awaiting_approval"
                )
                logger.info(
                    f"Smart Commit proposal prepared for execution ID {exec_id}. Awaiting user approval."
                )
                return {
                    "success": True,
                    "execution_id": exec_id,
                    "mode": "smart",
                    "status": "awaiting_approval",
                    "proposal": proposal_dict,
                }

        finally:
            lock.release()

    # =========================================================================
    # Step 2: Approve, Reject, or Edit Proposal
    # =========================================================================

    def approve_proposal(
        self, execution_id: int, approved_by: str = "user", notes: Optional[str] = None
    ) -> Dict[str, Any]:
        record = self.exec_repo.get_execution(execution_id)
        if not record:
            return {"success": False, "error": f"Execution ID {execution_id} not found."}

        if record.status not in ("awaiting_approval", "pending"):
            return {
                "success": False,
                "error": f"Cannot approve proposal in '{record.status}' status.",
            }

        self.exec_repo.set_approval(
            execution_id=execution_id,
            approval_status="approved",
            approved_by=approved_by,
            notes=notes,
        )
        self.exec_repo.update_execution(execution_id=execution_id, status="approved")
        logger.info(f"Execution proposal {execution_id} approved by {approved_by}.")
        return {"success": True, "execution_id": execution_id, "status": "approved"}

    def reject_proposal(
        self, execution_id: int, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        record = self.exec_repo.get_execution(execution_id)
        if not record:
            return {"success": False, "error": f"Execution ID {execution_id} not found."}

        self.exec_repo.set_approval(
            execution_id=execution_id,
            approval_status="rejected",
            approved_by="user",
            notes=reason,
        )
        self.exec_repo.update_execution(
            execution_id=execution_id,
            status="rejected",
            error_summary=reason or "Rejected by user.",
        )
        logger.info(f"Execution proposal {execution_id} rejected.")
        return {"success": True, "execution_id": execution_id, "status": "rejected"}

    def edit_proposal_message(
        self, execution_id: int, new_message: str
    ) -> Dict[str, Any]:
        record = self.exec_repo.get_execution(execution_id)
        if not record:
            return {"success": False, "error": f"Execution ID {execution_id} not found."}

        if not new_message or not new_message.strip():
            return {"success": False, "error": "Commit message cannot be empty."}

        # Update proposal data in DB
        proposal = json.loads(record.proposal_data or "{}")
        proposal["proposed_message"] = new_message.strip()
        self.exec_repo.update_execution(
            execution_id=execution_id,
            proposal_data=proposal,
            commit_message=new_message.strip(),
        )
        logger.info(f"Commit message updated for proposal {execution_id}.")
        return {
            "success": True,
            "execution_id": execution_id,
            "new_message": new_message.strip(),
        }

    # =========================================================================
    # Step 3: Execute Approved Proposal
    # =========================================================================

    def execute_proposal(self, execution_id: int) -> Dict[str, Any]:
        record = self.exec_repo.get_execution(execution_id)
        if not record:
            return {"success": False, "error": f"Execution ID {execution_id} not found."}

        if record.status != "approved":
            return {
                "success": False,
                "error": f"Execution ID {execution_id} cannot be executed (status is '{record.status}', expected 'approved').",
            }

        repo = self.db.get_repository(record.repository_id)
        if not repo:
            return {"success": False, "error": "Target repository record not found."}

        lock = self._get_repo_lock(record.repository_id)
        if not lock.acquire(blocking=False):
            return {
                "success": False,
                "error": f"Another Git execution is in progress for repository ID {record.repository_id}.",
            }

        try:
            repo_path = Path(repo.repository_path)
            proposal = json.loads(record.proposal_data or "{}")
            target_files = proposal.get("proposed_files", [])
            commit_msg = record.commit_message or proposal.get("proposed_message", "")
            automation_settings = self.exec_repo.get_automation_settings(record.repository_id)

            # Safety Recheck: Invalidate proposal if repo state changed
            git_mgr = GitManager(repo_path)
            current_status = git_mgr.get_git_status()
            changes = current_status["changes"]
            all_current_changed = set(
                changes.get("modified", [])
                + changes.get("untracked", [])
                + changes.get("deleted", [])
                + changes.get("staged_added", [])
                + changes.get("staged_modified", [])
                + changes.get("staged_deleted", [])
            )

            # If any of the proposed files no longer has changes, invalidate
            missing = [f for f in target_files if f not in all_current_changed]
            if missing:
                self.exec_repo.update_execution(
                    execution_id=execution_id,
                    status="invalidated",
                    error_summary=f"Stale proposal: files {missing} are no longer modified.",
                )
                return {
                    "success": False,
                    "error": f"Repository state changed since analysis. Stale proposal invalidated (missing changes for {missing}).",
                }

            return self._execute_commit_internal(
                execution_id=execution_id,
                repo_path=repo_path,
                target_files=target_files,
                commit_message=commit_msg,
                settings=automation_settings,
                approved_by="user",
            )
        finally:
            lock.release()

    def _execute_commit_internal(
        self,
        execution_id: int,
        repo_path: Path,
        target_files: List[str],
        commit_message: str,
        settings: RepositoryAutomationSettingsModel,
        approved_by: str,
    ) -> Dict[str, Any]:
        executor = GitExecutor(repo_path, database=self.db)
        res = executor.execute_commit(
            files_to_commit=target_files,
            commit_message=commit_message,
            settings=settings,
        )

        now = get_utc_now_iso()
        if res["success"]:
            self.exec_repo.update_execution(
                execution_id=execution_id,
                status="committed",
                commit_hash=res["commit_hash"],
                commit_message=commit_message,
                completed_at=now,
            )
            return {
                "success": True,
                "execution_id": execution_id,
                "commit_hash": res["commit_hash"],
                "short_hash": res.get("short_hash"),
                "branch": res.get("branch"),
                "committed_files": target_files,
                "message": "Commit created and verified successfully.",
            }
        else:
            self.exec_repo.update_execution(
                execution_id=execution_id,
                status="failed",
                error_summary=res.get("error"),
                completed_at=now,
            )
            return {
                "success": False,
                "execution_id": execution_id,
                "error": res.get("error"),
            }

