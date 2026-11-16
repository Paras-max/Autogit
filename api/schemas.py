"""
Pydantic schemas for API request and response validation (Phase 1 & Phase 2).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Phase 1 Schemas
# ============================================================================

class RepositoryCreateRequest(BaseModel):
    path: str = Field(..., description="Absolute or relative local path to Git repository")
    name: Optional[str] = Field(None, description="Optional custom name for repository")


class CommitInfoSchema(BaseModel):
    hexsha: str
    short_hash: str
    message: str
    author_name: str
    author_email: str
    authored_datetime: str
    committed_datetime: str


class RepositoryResponse(BaseModel):
    id: int
    repository_name: str
    repository_path: str
    remote_url: Optional[str] = None
    current_branch: Optional[str] = None
    created_at: str
    latest_commit: Optional[CommitInfoSchema] = None
    name: Optional[str] = None
    path: Optional[str] = None
    repo_id: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class RepositorySummaryResponse(BaseModel):
    id: int
    repository_name: str
    repository_path: str
    remote_url: Optional[str] = None
    current_branch: Optional[str] = None
    created_at: str
    name: Optional[str] = None
    path: Optional[str] = None
    repo_id: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class GitStatusResponse(BaseModel):
    repository_path: str
    current_branch: str
    is_clean: bool
    remote_url: Optional[str] = None
    remotes: List[Dict[str, str]] = []
    latest_commit: Optional[CommitInfoSchema] = None
    staged_files: List[str] = []
    unstaged_files: List[str] = []
    changes: Dict[str, List[str]]


class GitBranchesResponse(BaseModel):
    current_branch: str
    branches: List[str]


class GitDiffResponse(BaseModel):
    unstaged: str
    staged: str


class GitHubValidateRequest(BaseModel):
    token: Optional[str] = Field(None, description="Optional GitHub Personal Access Token")


class GitHubValidateResponse(BaseModel):
    success: bool
    provider: str
    status: str
    username: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    token_preview: Optional[str] = None


class GitIdentityRequest(BaseModel):
    name: str = Field(..., description="Git author name")
    email: str = Field(..., description="Git author email")


class GitIdentityResponse(BaseModel):
    name: str
    email: str


class AIProviderSelectRequest(BaseModel):
    provider: str = Field(..., description="AI provider (e.g. openai, anthropic, gemini)")


class OverallAuthStatusResponse(BaseModel):
    github: Dict[str, Any]
    git_identity: Dict[str, Optional[str]]
    ai_providers: Dict[str, Any]


class MonitoringStatusResponse(BaseModel):
    repository_id: int
    repository_name: str
    is_active: bool
    reconciliation_running: bool


class FileEventResponse(BaseModel):
    id: Optional[int]
    repository_id: int
    file_path: str
    event_type: str
    timestamp: str
    processed_status: str

    model_config = ConfigDict(from_attributes=True)


class GenericMessageResponse(BaseModel):
    success: bool
    message: str


# ============================================================================
# Phase 2 Schemas
# ============================================================================

class AutomationSettingsSchema(BaseModel):
    repository_id: int
    execution_mode: str = "smart"  # 'smart' or 'auto'
    auto_commit_enabled: bool = False
    push_enabled: bool = False
    protected_branches: List[str] = ["main", "master"]
    validation_required: bool = True
    quiet_period_seconds: float = 3.0


class UpdateAutomationSettingsRequest(BaseModel):
    execution_mode: Optional[str] = None
    auto_commit_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    protected_branches: Optional[List[str]] = None
    validation_required: Optional[bool] = None
    quiet_period_seconds: Optional[float] = None


class AnalyzeRequest(BaseModel):
    user_hint: Optional[str] = None
    execution_mode: Optional[str] = None


class ProposalApproveRequest(BaseModel):
    approved_by: str = "user"
    notes: Optional[str] = None


class ProposalRejectRequest(BaseModel):
    reason: Optional[str] = None


class ProposalEditMessageRequest(BaseModel):
    new_message: str = Field(..., min_length=1)


class ModeUpdateRequest(BaseModel):
    mode: str = Field(..., pattern="^(smart|auto)$")
    enable_auto_commit: Optional[bool] = False


# ============================================================================
# Phase 3 Schemas
# ============================================================================

class RepositoryPermissionResponse(BaseModel):
    repository_id: int
    monitoring_enabled: bool
    ai_analysis_enabled: bool
    autonomous_development_enabled: bool
    smart_commit_enabled: bool
    auto_commit_enabled: bool
    remote_push_enabled: bool
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateRepositoryPermissionRequest(BaseModel):
    monitoring_enabled: Optional[bool] = None
    ai_analysis_enabled: Optional[bool] = None
    autonomous_development_enabled: Optional[bool] = None
    smart_commit_enabled: Optional[bool] = None
    auto_commit_enabled: Optional[bool] = None
    remote_push_enabled: Optional[bool] = None


class ScheduledSessionResponse(BaseModel):
    id: Optional[int]
    schedule_id: int
    scheduled_date: str
    day_of_week: int
    time_window: str
    status: str
    executed_at: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WeeklyScheduleResponse(BaseModel):
    id: Optional[int]
    week_identifier: str
    year: int
    week_number: int
    timezone: str
    is_active: bool
    created_at: str
    sessions: List[ScheduledSessionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class GenerateScheduleRequest(BaseModel):
    force_regenerate: bool = False
    timezone: Optional[str] = None


class DevelopmentTaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    task_type: str = "feature"  # 'feature', 'test', 'refactor', 'documentation', 'bugfix'
    priority: str = "medium"  # 'low', 'medium', 'high'


class DevelopmentTaskResponse(BaseModel):
    id: Optional[int]
    repository_id: int
    title: str
    description: Optional[str] = None
    task_type: str
    status: str
    priority: str
    created_at: str
    completed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectContextResponse(BaseModel):
    id: Optional[int]
    repository_id: int
    project_type: str
    primary_language: str
    framework: Optional[str] = None
    test_framework: Optional[str] = None
    summary: Optional[str] = None
    analyzed_at: str

    model_config = ConfigDict(from_attributes=True)


class DevelopmentSessionResponse(BaseModel):
    session_id: int
    repository_id: int
    status: str
    branch_name: str
    files_modified: List[str] = []
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    tasks_summary: str = ""
    error_message: Optional[str] = None


class RunDevelopmentRequest(BaseModel):
    isolated_worktree: bool = True


# ============================================================================
# Phase 4 Schemas
# ============================================================================

class RemoteStatusResponse(BaseModel):
    id: Optional[int]
    repository_id: int
    local_branch: str
    remote_branch: str
    ahead_count: int
    behind_count: int
    last_fetch_at: Optional[str] = None
    last_push_at: Optional[str] = None
    sync_status: str

    model_config = ConfigDict(from_attributes=True)


class SyncOperationResponse(BaseModel):
    success: bool
    operation: str
    branch: Optional[str] = None
    target_branch: Optional[str] = None
    remote: Optional[str] = None
    commit_hash: Optional[str] = None
    local_commit_hash: Optional[str] = None
    remote_commit_hash: Optional[str] = None
    ahead_count: Optional[int] = None
    behind_count: Optional[int] = None
    sync_status: Optional[str] = None
    push_sync_status: Optional[str] = None
    verification_status: Optional[str] = None
    remote_verified: Optional[bool] = None
    remote_advanced: Optional[bool] = None
    execution_id: Optional[int] = None
    last_push_at: Optional[str] = None
    pushed: Optional[bool] = None
    message: Optional[str] = None
    error: Optional[str] = None
    conflict: Optional[bool] = False
    conflicting_files: Optional[List[str]] = []


class AdditionalCommitItem(BaseModel):
    commit_hash: str
    short_hash: str
    commit_message: str
    author: Optional[str] = None
    date: Optional[str] = None


class GitHubPushPreviewRequest(BaseModel):
    repository_id: int
    execution_id: Optional[int] = None
    commit_hash: Optional[str] = None
    branch: Optional[str] = None
    remote_name: Optional[str] = "origin"
    target_branch: Optional[str] = None


class GitHubPushPreviewResponse(BaseModel):
    repository_id: int
    source_branch: str
    target_branch: str
    remote_name: str
    selected_commit_hash: str
    selected_commit_message: Optional[str] = None
    branch_head_hash: str
    is_branch_head: bool
    has_additional_commits: bool
    additional_commits_count: int
    additional_commits: List[AdditionalCommitItem] = []
    total_commits_to_push_count: int


class GitHubPushRequest(BaseModel):
    repository_id: int
    execution_id: Optional[int] = None
    commit_id: Optional[int] = None
    commit_hash: Optional[str] = None
    remote_name: Optional[str] = "origin"
    target_branch: Optional[str] = None
    branch: Optional[str] = None
    confirm_descendants: Optional[bool] = False
    expected_head: Optional[str] = None


class GitHubSyncHistoryResponse(BaseModel):
    id: int
    repository_id: int
    operation_type: str
    branch: str
    status: str
    commit_hash: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    error_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseModel):
    id: int
    repository_id: Optional[int] = None
    notification_type: str
    title: str
    message: str
    severity: str
    is_read: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class DashboardOverviewResponse(BaseModel):
    total_repositories: int
    authorized_repositories: int
    active_sessions: int
    total_commits: int
    pending_approvals: int
    validation_failures: int
    monitoring_active: bool
    scheduler_active: bool
    current_week: str
    agents_online: int


class DashboardActivityItem(BaseModel):
    id: str
    type: str  # 'commit', 'proposal', 'session', 'sync', 'file_event'
    repository_id: Optional[int] = None
    repository_name: Optional[str] = None
    title: str
    description: str
    timestamp: str
    status: str


class CommitDetailResponse(BaseModel):
    commit_hash: str
    short_hash: str
    message: str
    author: str
    date: str
    branch: str
    repository_id: int
    repository_name: str
    files_changed: List[str] = []
    github_commit_url: Optional[str] = None
    validation_status: Optional[str] = None


class ServiceStatusResponse(BaseModel):
    is_running: bool
    pid: Optional[int] = None
    lock_file: str
    uptime_seconds: Optional[int] = None
    status: str = "running"


# ============================================================================
# GitHub Import Schema
# ============================================================================

class GitHubImportRequest(BaseModel):
    """Request body for cloning a GitHub repository and registering it locally."""
    github_url: str = Field(
        ...,
        description="HTTPS or SSH GitHub URL (e.g. https://github.com/owner/repo.git)",
    )
    destination_folder: str = Field(
        ...,
        description="Local folder path to clone the repository INTO",
    )
    name: Optional[str] = Field(
        None,
        description="Optional custom name override for the repository",
    )

