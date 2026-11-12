"""
FastAPI route handlers for AutoGit AI Phase 2 automation, proposals, and execution.
"""

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.routes import get_db
from api.schemas import (
    AnalyzeRequest,
    AutomationSettingsSchema,
    GenericMessageResponse,
    ModeUpdateRequest,
    ProposalApproveRequest,
    ProposalEditMessageRequest,
    ProposalRejectRequest,
    UpdateAutomationSettingsRequest,
)
from core.execution_controller import ExecutionController
from core.git_manager import GitManager
from database.db import DatabaseManager
from database.execution_repository import ExecutionRepository
from database.models import RepositoryAutomationSettingsModel
from utils.logger import logger
from utils.security import verify_local_access


execution_router = APIRouter(prefix="/automation", tags=["automation"])


# Dependencies
def get_exec_repo(database: DatabaseManager = Depends(get_db)) -> ExecutionRepository:
    return ExecutionRepository(database)


def get_controller(
    database: DatabaseManager = Depends(get_db),
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
) -> ExecutionController:
    return ExecutionController(database=database, exec_repo=exec_repo)


def check_auth(authorization: Optional[str] = Header(None)):
    if not verify_local_access(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing local authorization token.",
        )


# ============================================================================
# Automation Settings
# ============================================================================

@execution_router.get(
    "/settings/{repository_id}",
    response_model=AutomationSettingsSchema,
    summary="Get automation settings for repository",
)
def get_settings(
    repository_id: int,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
    database: DatabaseManager = Depends(get_db),
):
    if not database.get_repository(repository_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository ID {repository_id} not found.",
        )
    return exec_repo.get_automation_settings(repository_id)


@execution_router.post(
    "/settings/{repository_id}",
    response_model=AutomationSettingsSchema,
    summary="Update automation settings for repository",
    dependencies=[Depends(check_auth)],
)
def update_settings(
    repository_id: int,
    payload: UpdateAutomationSettingsRequest,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
    database: DatabaseManager = Depends(get_db),
):
    if not database.get_repository(repository_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository ID {repository_id} not found.",
        )

    current = exec_repo.get_automation_settings(repository_id)

    # If user attempts to set auto_commit_enabled=True, ensure mode is explicitly 'auto'
    new_mode = payload.execution_mode if payload.execution_mode else current.execution_mode
    new_auto_commit = (
        payload.auto_commit_enabled
        if payload.auto_commit_enabled is not None
        else current.auto_commit_enabled
    )

    updated = RepositoryAutomationSettingsModel(
        repository_id=repository_id,
        execution_mode=new_mode,
        auto_commit_enabled=new_auto_commit,
        push_enabled=payload.push_enabled if payload.push_enabled is not None else current.push_enabled,
        protected_branches=(
            payload.protected_branches
            if payload.protected_branches is not None
            else current.protected_branches
        ),
        validation_required=(
            payload.validation_required
            if payload.validation_required is not None
            else current.validation_required
        ),
        quiet_period_seconds=(
            payload.quiet_period_seconds
            if payload.quiet_period_seconds is not None
            else current.quiet_period_seconds
        ),
    )
    return exec_repo.save_automation_settings(updated)


# ============================================================================
# Mode Selection
# ============================================================================

@execution_router.get(
    "/mode/{repository_id}",
    summary="Get current execution mode and auto commit status",
)
def get_mode(
    repository_id: int,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
    database: DatabaseManager = Depends(get_db),
):
    if not database.get_repository(repository_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository ID {repository_id} not found.",
        )
    s = exec_repo.get_automation_settings(repository_id)
    return {
        "repository_id": repository_id,
        "execution_mode": s.execution_mode,
        "auto_commit_enabled": s.auto_commit_enabled,
        "push_enabled": s.push_enabled,
    }


@execution_router.post(
    "/mode/{repository_id}",
    summary="Set execution mode ('smart' or 'auto')",
    dependencies=[Depends(check_auth)],
)
def set_mode(
    repository_id: int,
    payload: ModeUpdateRequest,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
    database: DatabaseManager = Depends(get_db),
):
    if not database.get_repository(repository_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository ID {repository_id} not found.",
        )
    s = exec_repo.get_automation_settings(repository_id)
    s.execution_mode = payload.mode
    if payload.mode == "auto":
        # Auto Commit must be explicitly confirmed
        s.auto_commit_enabled = bool(payload.enable_auto_commit)
    else:
        s.auto_commit_enabled = False

    exec_repo.save_automation_settings(s)
    return {
        "success": True,
        "repository_id": repository_id,
        "execution_mode": s.execution_mode,
        "auto_commit_enabled": s.auto_commit_enabled,
    }


# ============================================================================
# Analysis & Proposals
# ============================================================================

@execution_router.post(
    "/analyze/{repository_id}",
    summary="Analyze working directory changes and prepare commit proposal",
    dependencies=[Depends(check_auth)],
)
async def analyze_repository(
    repository_id: int,
    payload: AnalyzeRequest,
    controller: ExecutionController = Depends(get_controller),
):
    res = await controller.analyze_and_propose(
        repository_id=repository_id,
        user_hint=payload.user_hint,
        execution_mode=payload.execution_mode,
    )
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
    return res


@execution_router.get(
    "/analysis/{execution_id}",
    summary="Retrieve analysis proposal details by execution ID",
)
def get_analysis(
    execution_id: int,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
):
    rec = exec_repo.get_execution(execution_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution ID {execution_id} not found.",
        )
    proposal = json.loads(rec.proposal_data or "{}")
    groups = [asdict(g) for g in exec_repo.get_change_groups(execution_id)]
    val_results = [asdict(v) for v in exec_repo.get_validation_results(execution_id)]

    return {
        "execution_id": rec.id,
        "repository_id": rec.repository_id,
        "execution_mode": rec.execution_mode,
        "status": rec.status,
        "created_at": rec.created_at,
        "proposal": proposal,
        "groups": groups,
        "validation_results": val_results,
    }


@execution_router.get(
    "/proposals/{repository_id}",
    summary="Get active pending proposal for repository",
)
def get_active_proposal(
    repository_id: int,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
):
    rec = exec_repo.get_active_proposal(repository_id)
    if not rec:
        return {"active_proposal": None}
    proposal = json.loads(rec.proposal_data or "{}")
    return {
        "active_proposal": {
            "execution_id": rec.id,
            "status": rec.status,
            "proposal": proposal,
        }
    }


@execution_router.post(
    "/proposals/{execution_id}/approve",
    summary="Approve a Smart Commit proposal",
    dependencies=[Depends(check_auth)],
)
def approve_proposal(
    execution_id: int,
    payload: ProposalApproveRequest,
    controller: ExecutionController = Depends(get_controller),
):
    res = controller.approve_proposal(
        execution_id=execution_id,
        approved_by=payload.approved_by,
        notes=payload.notes,
    )
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
    return res


@execution_router.post(
    "/proposals/{execution_id}/reject",
    summary="Reject a Smart Commit proposal",
    dependencies=[Depends(check_auth)],
)
def reject_proposal(
    execution_id: int,
    payload: ProposalRejectRequest,
    controller: ExecutionController = Depends(get_controller),
):
    res = controller.reject_proposal(execution_id=execution_id, reason=payload.reason)
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
    return res


@execution_router.post(
    "/proposals/{execution_id}/edit-message",
    summary="Edit the proposed commit message",
    dependencies=[Depends(check_auth)],
)
def edit_proposal_message(
    execution_id: int,
    payload: ProposalEditMessageRequest,
    controller: ExecutionController = Depends(get_controller),
):
    res = controller.edit_proposal_message(
        execution_id=execution_id, new_message=payload.new_message
    )
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
    return res


# ============================================================================
# Execution
# ============================================================================

@execution_router.post(
    "/execute/{execution_id}",
    summary="Execute an approved commit proposal",
    dependencies=[Depends(check_auth)],
)
def execute_approved(
    execution_id: int,
    controller: ExecutionController = Depends(get_controller),
):
    res = controller.execute_proposal(execution_id=execution_id)
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
    return res


@execution_router.get(
    "/executions/{repository_id}",
    summary="List past executions for repository",
)
def list_executions(
    repository_id: int,
    limit: int = 50,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
):
    recs = exec_repo.list_executions(repository_id, limit=limit)
    return [
        {
            "id": r.id,
            "repository_id": r.repository_id,
            "execution_mode": r.execution_mode,
            "status": r.status,
            "commit_hash": r.commit_hash,
            "commit_message": r.commit_message,
            "created_at": r.created_at,
            "completed_at": r.completed_at,
            "error_summary": r.error_summary,
        }
        for r in recs
    ]


# ============================================================================
# Validation Endpoints
# ============================================================================

@execution_router.post(
    "/validate/{repository_id}",
    summary="Run all pre-commit validation checks for repository",
    dependencies=[Depends(check_auth)],
)
def run_validations(
    repository_id: int,
    controller: ExecutionController = Depends(get_controller),
    database: DatabaseManager = Depends(get_db),
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
):
    repo = database.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository ID {repository_id} not found.",
        )
    git_mgr = GitManager(repo.repository_path)
    status_data = git_mgr.get_git_status()
    all_files = status_data["unstaged_files"] + status_data["staged_files"]
    settings = exec_repo.get_automation_settings(repository_id)

    report = controller.validation_agent.run_all_validations(
        repo_path=repo.repository_path,
        current_branch=status_data["current_branch"],
        target_files=all_files,
        total_diff_chars=len(git_mgr.get_unstaged_diff()) + len(git_mgr.get_staged_diff()),
        settings=settings,
    )
    return report


@execution_router.get(
    "/validation/{execution_id}",
    summary="Get validation results for execution ID",
)
def get_validation_results(
    execution_id: int,
    exec_repo: ExecutionRepository = Depends(get_exec_repo),
):
    return [asdict(v) for v in exec_repo.get_validation_results(execution_id)]
