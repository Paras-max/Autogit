"""
FastAPI route handlers for AutoGit AI.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import (
    AIProviderSelectRequest,
    FileEventResponse,
    GenericMessageResponse,
    GitHubValidateRequest,
    GitHubValidateResponse,
    GitBranchesResponse,
    GitDiffResponse,
    GitIdentityRequest,
    GitIdentityResponse,
    GitStatusResponse,
    MonitoringStatusResponse,
    OverallAuthStatusResponse,
    RepositoryCreateRequest,
    RepositoryResponse,
    RepositorySummaryResponse,
)
from core.authentication import AuthenticationService
from core.credential_manager import CredentialManager
from core.git_manager import GitManager
from core.repository_manager import RepositoryManager
from database.db import DatabaseManager, db
from monitoring.file_monitor import FileMonitor, file_monitor
from utils.logger import logger


api_router = APIRouter()


# Dependency injection helpers
def get_db() -> DatabaseManager:
    return db


def get_repo_manager(database: DatabaseManager = Depends(get_db)) -> RepositoryManager:
    return RepositoryManager(database)


def get_cred_manager(database: DatabaseManager = Depends(get_db)) -> CredentialManager:
    return CredentialManager(database)


def get_auth_service(
    database: DatabaseManager = Depends(get_db),
    cred_manager: CredentialManager = Depends(get_cred_manager),
) -> AuthenticationService:
    return AuthenticationService(database, cred_manager)


def get_monitor() -> FileMonitor:
    return file_monitor


# --- Repository Endpoints ---

@api_router.post(
    "/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a local Git repository",
)
def create_repository(
    payload: RepositoryCreateRequest,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
):
    try:
        repo = repo_mgr.add_repository(payload.path, payload.name)
        info = repo_mgr.get_repository_info(repo.id)  # type: ignore
        return info
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error registering repository: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Registration failed: {e}"
        )


@api_router.get(
    "/repositories",
    response_model=List[RepositorySummaryResponse],
    summary="List all registered repositories",
)
def list_repositories(repo_mgr: RepositoryManager = Depends(get_repo_manager)):
    return repo_mgr.list_repositories()


@api_router.get(
    "/repositories/{repo_id}",
    response_model=RepositoryResponse,
    summary="Get repository details by ID",
)
def get_repository(repo_id: int, repo_mgr: RepositoryManager = Depends(get_repo_manager)):
    info = repo_mgr.get_repository_info(repo_id)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repo_id} not found",
        )
    return info


@api_router.delete(
    "/repositories/{repo_id}",
    response_model=GenericMessageResponse,
    summary="Remove repository from application",
)
def delete_repository(
    repo_id: int,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
    monitor: FileMonitor = Depends(get_monitor),
):
    # Ensure monitoring stopped before removal
    if monitor.is_monitoring(repo_id):
        monitor.stop_monitoring(repo_id)

    removed = repo_mgr.remove_repository(repo_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repo_id} not found",
        )
    return GenericMessageResponse(
        success=True,
        message=f"Repository ID {repo_id} removed from application (files untouched).",
    )


# --- Git Endpoints ---

def _get_git_mgr(repo_id: int, repo_mgr: RepositoryManager) -> GitManager:
    repo = repo_mgr.db.get_repository(repo_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repo_id} not found",
        )
    try:
        return GitManager(repo.repository_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Git operation failed: {e}",
        )


@api_router.get(
    "/repositories/{repo_id}/status",
    response_model=GitStatusResponse,
    summary="Get Git status for repository",
)
def get_git_status(
    repo_id: int,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
):
    git_mgr = _get_git_mgr(repo_id, repo_mgr)
    return git_mgr.get_git_status()


@api_router.get(
    "/repositories/{repo_id}/branches",
    response_model=GitBranchesResponse,
    summary="Get branch information",
)
def get_git_branches(
    repo_id: int,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
):
    git_mgr = _get_git_mgr(repo_id, repo_mgr)
    return GitBranchesResponse(
        current_branch=git_mgr.get_current_branch(),
        branches=git_mgr.get_branches(),
    )


@api_router.get(
    "/repositories/{repo_id}/diff",
    response_model=GitDiffResponse,
    summary="Get staged and unstaged diffs",
)
def get_git_diff(
    repo_id: int,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
):
    git_mgr = _get_git_mgr(repo_id, repo_mgr)
    return git_mgr.get_diff()


@api_router.get(
    "/repositories/{repo_id}/commits/latest",
    summary="Get latest commit information",
)
def get_latest_commit(
    repo_id: int,
    repo_mgr: RepositoryManager = Depends(get_repo_manager),
):
    git_mgr = _get_git_mgr(repo_id, repo_mgr)
    commit = git_mgr.get_latest_commit()
    if not commit:
        return {"message": "No commits found in repository"}
    return commit


# --- Authentication Endpoints ---

@api_router.post(
    "/auth/github/validate",
    response_model=GitHubValidateResponse,
    summary="Validate GitHub Personal Access Token",
)
async def validate_github(
    payload: GitHubValidateRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    result = await auth_service.validate_github_token(payload.token)
    return result


@api_router.get(
    "/auth/status",
    response_model=OverallAuthStatusResponse,
    summary="Get authentication and provider status",
)
def get_auth_status(
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    return auth_service.get_overall_auth_status()


@api_router.post(
    "/auth/git-identity",
    response_model=GitIdentityResponse,
    summary="Configure Git author name and email override",
)
def set_git_identity(
    payload: GitIdentityRequest,
    cred_mgr: CredentialManager = Depends(get_cred_manager),
):
    try:
        identity = cred_mgr.set_git_identity_override(payload.name, payload.email)
        return identity
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_router.post(
    "/auth/ai-provider",
    response_model=GenericMessageResponse,
    summary="Select active AI provider",
)
def select_ai_provider(
    payload: AIProviderSelectRequest,
    cred_mgr: CredentialManager = Depends(get_cred_manager),
):
    try:
        chosen = cred_mgr.set_active_ai_provider(payload.provider)
        return GenericMessageResponse(
            success=True,
            message=f"Active AI provider set to: {chosen}",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- Monitoring Endpoints ---

@api_router.post(
    "/monitoring/start/{repo_id}",
    response_model=GenericMessageResponse,
    summary="Start monitoring repository directory",
)
def start_monitoring(
    repo_id: int,
    monitor: FileMonitor = Depends(get_monitor),
):
    started = monitor.start_monitoring(repo_id)
    if not started:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not start monitoring for repository ID {repo_id}",
        )
    return GenericMessageResponse(
        success=True,
        message=f"Monitoring started for repository ID {repo_id}",
    )


@api_router.post(
    "/monitoring/stop/{repo_id}",
    response_model=GenericMessageResponse,
    summary="Stop monitoring repository directory",
)
def stop_monitoring(
    repo_id: int,
    monitor: FileMonitor = Depends(get_monitor),
):
    stopped = monitor.stop_monitoring(repo_id)
    if not stopped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not stop monitoring for repository ID {repo_id} (may not be active)",
        )
    return GenericMessageResponse(
        success=True,
        message=f"Monitoring stopped for repository ID {repo_id}",
    )


@api_router.get(
    "/monitoring/status/{repo_id}",
    response_model=MonitoringStatusResponse,
    summary="Get monitoring status for repository",
)
def get_monitoring_status(
    repo_id: int,
    monitor: FileMonitor = Depends(get_monitor),
):
    return monitor.get_status(repo_id)


@api_router.get(
    "/monitoring/events/{repo_id}",
    response_model=List[FileEventResponse],
    summary="List recorded file events for repository",
)
def get_monitoring_events(
    repo_id: int,
    limit: int = 100,
    database: DatabaseManager = Depends(get_db),
):
    events = database.list_file_events(repo_id, limit=limit)
    return events

