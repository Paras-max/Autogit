"""
FastAPI route handlers for AutoGit AI Phase 3:
- Repository Permission Management
- Weekly 5-Day Random Scheduler
- Autonomous Development Sessions and Tasks
"""

import dataclasses
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from api.routes import get_db
from api.schemas import (
    DevelopmentSessionResponse,
    DevelopmentTaskCreateRequest,
    DevelopmentTaskResponse,
    GenerateScheduleRequest,
    GenericMessageResponse,
    ProjectContextResponse,
    RepositoryPermissionResponse,
    RunDevelopmentRequest,
    ScheduledSessionResponse,
    UpdateRepositoryPermissionRequest,
    WeeklyScheduleResponse,
)
from agents.development_agent import DevelopmentAgent
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager
from database.permission_repository import PermissionRepository
from database.schedule_repository import ScheduleRepository
from development.project_analyzer import ProjectAnalyzer
from development.task_manager import TaskManager
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger


phase3_router = APIRouter()


# Dependency injection helpers
def get_permission_mgr(database: DatabaseManager = Depends(get_db)) -> PermissionManager:
    return PermissionManager(database)


def get_weekly_scheduler(database: DatabaseManager = Depends(get_db)) -> WeeklyScheduler:
    return WeeklyScheduler(database)


def get_task_mgr(database: DatabaseManager = Depends(get_db)) -> TaskManager:
    return TaskManager(database)


def get_project_analyzer(database: DatabaseManager = Depends(get_db)) -> ProjectAnalyzer:
    return ProjectAnalyzer(database)


def get_development_agent(database: DatabaseManager = Depends(get_db)) -> DevelopmentAgent:
    return DevelopmentAgent(database)


# ============================================================================
# 1. Repository Permissions Endpoints
# ============================================================================

@phase3_router.get(
    "/repositories/{repository_id}/permissions",
    response_model=RepositoryPermissionResponse,
    summary="Get repository permissions",
)
def get_repository_permissions(
    repository_id: int,
    permission_mgr: PermissionManager = Depends(get_permission_mgr),
):
    try:
        perms = permission_mgr.get_permissions(repository_id)
        return RepositoryPermissionResponse(**dataclasses.asdict(perms))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase3_router.put(
    "/repositories/{repository_id}/permissions",
    response_model=RepositoryPermissionResponse,
    summary="Update repository permissions",
)
def update_repository_permissions(
    repository_id: int,
    request: UpdateRepositoryPermissionRequest,
    permission_mgr: PermissionManager = Depends(get_permission_mgr),
):
    try:
        updated = permission_mgr.update_permissions(
            repository_id=repository_id,
            monitoring_enabled=request.monitoring_enabled,
            ai_analysis_enabled=request.ai_analysis_enabled,
            autonomous_development_enabled=request.autonomous_development_enabled,
            smart_commit_enabled=request.smart_commit_enabled,
            auto_commit_enabled=request.auto_commit_enabled,
            remote_push_enabled=request.remote_push_enabled,
            pull_request_creation_enabled=request.pull_request_creation_enabled,
        )
        return RepositoryPermissionResponse(**dataclasses.asdict(updated))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase3_router.post(
    "/repositories/{repository_id}/permissions/enable-development",
    response_model=RepositoryPermissionResponse,
    summary="Enable autonomous development permission for a repository",
)
def enable_autonomous_development(
    repository_id: int,
    permission_mgr: PermissionManager = Depends(get_permission_mgr),
):
    try:
        updated = permission_mgr.enable_autonomous_development(repository_id)
        return RepositoryPermissionResponse(**dataclasses.asdict(updated))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase3_router.post(
    "/repositories/{repository_id}/permissions/disable-development",
    response_model=RepositoryPermissionResponse,
    summary="Disable autonomous development permission for a repository",
)
def disable_autonomous_development(
    repository_id: int,
    permission_mgr: PermissionManager = Depends(get_permission_mgr),
):
    try:
        updated = permission_mgr.disable_autonomous_development(repository_id)
        return RepositoryPermissionResponse(**dataclasses.asdict(updated))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase3_router.post(
    "/repositories/{repository_id}/permissions/revoke",
    response_model=RepositoryPermissionResponse,
    summary="Revoke all permissions for a repository",
)
def revoke_all_permissions(
    repository_id: int,
    permission_mgr: PermissionManager = Depends(get_permission_mgr),
):
    try:
        revoked = permission_mgr.revoke_all_permissions(repository_id)
        return RepositoryPermissionResponse(**dataclasses.asdict(revoked))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============================================================================
# 2. Weekly 5-Day Random Scheduler Endpoints
# ============================================================================

@phase3_router.get(
    "/scheduler/weekly",
    response_model=WeeklyScheduleResponse,
    summary="Get current weekly schedule and scheduled days",
)
def get_current_weekly_schedule(
    scheduler: WeeklyScheduler = Depends(get_weekly_scheduler),
    db_mgr: DatabaseManager = Depends(get_db),
):
    schedule, sessions = scheduler.get_or_create_current_week_schedule()
    session_responses = [ScheduledSessionResponse(**dataclasses.asdict(s)) for s in sessions]
    return WeeklyScheduleResponse(
        id=schedule.id,
        week_identifier=schedule.week_identifier,
        year=schedule.year,
        week_number=schedule.week_number,
        timezone=schedule.timezone,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
        sessions=session_responses,
    )


@phase3_router.post(
    "/scheduler/generate",
    response_model=WeeklyScheduleResponse,
    summary="Generate or regenerate a 5-day random schedule",
)
def generate_weekly_schedule(
    request: GenerateScheduleRequest,
    scheduler: WeeklyScheduler = Depends(get_weekly_scheduler),
):
    schedule, sessions = scheduler.get_or_create_current_week_schedule(
        force_regenerate=request.force_regenerate
    )
    session_responses = [ScheduledSessionResponse(**dataclasses.asdict(s)) for s in sessions]
    return WeeklyScheduleResponse(
        id=schedule.id,
        week_identifier=schedule.week_identifier,
        year=schedule.year,
        week_number=schedule.week_number,
        timezone=schedule.timezone,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
        sessions=session_responses,
    )


@phase3_router.post(
    "/scheduler/pause",
    response_model=GenericMessageResponse,
    summary="Pause the autonomous development scheduler",
)
def pause_scheduler(scheduler: WeeklyScheduler = Depends(get_weekly_scheduler)):
    scheduler.pause()
    return GenericMessageResponse(success=True, message="Scheduler paused successfully.")


@phase3_router.post(
    "/scheduler/resume",
    response_model=GenericMessageResponse,
    summary="Resume the autonomous development scheduler",
)
def resume_scheduler(scheduler: WeeklyScheduler = Depends(get_weekly_scheduler)):
    scheduler.resume()
    return GenericMessageResponse(success=True, message="Scheduler resumed successfully.")


@phase3_router.get(
    "/scheduler/status",
    summary="Get current scheduler status and today's schedule",
)
def get_scheduler_status(scheduler: WeeklyScheduler = Depends(get_weekly_scheduler)):
    is_active = scheduler.is_active()
    is_scheduled_today, session = scheduler.is_today_scheduled()
    current_time = scheduler.get_current_time().isoformat()
    return {
        "is_active": is_active,
        "timezone": scheduler.tz_name,
        "current_time": current_time,
        "is_scheduled_today": is_scheduled_today,
        "today_session": dataclasses.asdict(session) if session else None,
    }


# ============================================================================
# 3. Project Context & Tasks Endpoints
# ============================================================================

@phase3_router.get(
    "/development/{repository_id}/context",
    response_model=ProjectContextResponse,
    summary="Get cached project context",
)
def get_project_context(
    repository_id: int,
    analyzer: ProjectAnalyzer = Depends(get_project_analyzer),
):
    ctx = analyzer.get_context(repository_id)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project context not yet analyzed for repo {repository_id}.",
        )
    return ProjectContextResponse(**dataclasses.asdict(ctx))


@phase3_router.post(
    "/development/{repository_id}/analyze",
    response_model=ProjectContextResponse,
    summary="Trigger project context analysis",
)
def analyze_project(
    repository_id: int,
    db_mgr: DatabaseManager = Depends(get_db),
    analyzer: ProjectAnalyzer = Depends(get_project_analyzer),
):
    repo = db_mgr.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} does not exist.",
        )
    ctx = analyzer.analyze_repository(repository_id, repo.repository_path)
    return ProjectContextResponse(**dataclasses.asdict(ctx))


@phase3_router.get(
    "/development/{repository_id}/tasks",
    response_model=List[DevelopmentTaskResponse],
    summary="Get pending development tasks for repository",
)
def list_tasks(
    repository_id: int,
    task_mgr: TaskManager = Depends(get_task_mgr),
):
    tasks = task_mgr.get_pending_tasks(repository_id)
    return [DevelopmentTaskResponse(**dataclasses.asdict(t)) for t in tasks]


@phase3_router.post(
    "/development/{repository_id}/tasks",
    response_model=DevelopmentTaskResponse,
    summary="Add a new development task to repository backlog",
)
def add_task(
    repository_id: int,
    request: DevelopmentTaskCreateRequest,
    task_mgr: TaskManager = Depends(get_task_mgr),
    db_mgr: DatabaseManager = Depends(get_db),
):
    repo = db_mgr.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} does not exist.",
        )
    task = task_mgr.add_task(
        repository_id=repository_id,
        title=request.title,
        description=request.description,
        task_type=request.task_type,
        priority=request.priority,
    )
    return DevelopmentTaskResponse(**dataclasses.asdict(task))


# ============================================================================
# 4. Autonomous Development Execution Endpoints
# ============================================================================

@phase3_router.post(
    "/development/{repository_id}/run",
    response_model=DevelopmentSessionResponse,
    summary="Execute an autonomous development session",
)
def run_development_session(
    repository_id: int,
    request: RunDevelopmentRequest = RunDevelopmentRequest(),
    dev_agent: DevelopmentAgent = Depends(get_development_agent),
):
    try:
        res = dev_agent.run_development_session(
            repository_id=repository_id,
            isolated_worktree=request.isolated_worktree,
        )
        return DevelopmentSessionResponse(
            session_id=res.session_id,
            repository_id=res.repository_id,
            status=res.status,
            branch_name=res.branch_name,
            files_modified=res.files_modified,
            commit_hash=res.commit_hash,
            commit_message=res.commit_message,
            tasks_summary=res.tasks_summary,
            error_message=res.error_message,
        )
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

