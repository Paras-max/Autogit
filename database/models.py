"""
Data models for AutoGit AI database entities (Phase 1 & Phase 2).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --- Phase 1 Models ---

@dataclass
class RepositoryModel:
    id: Optional[int]
    repository_name: str
    repository_path: str
    remote_url: Optional[str]
    current_branch: Optional[str]
    created_at: str


@dataclass
class AuthenticationModel:
    id: Optional[int]
    provider: str
    username: Optional[str]
    authentication_status: str
    last_validated_at: Optional[str]


@dataclass
class FileEventModel:
    id: Optional[int]
    repository_id: int
    file_path: str
    event_type: str
    timestamp: str
    processed_status: str = "pending"


@dataclass
class SettingModel:
    id: Optional[int]
    setting_key: str
    setting_value: str
    updated_at: str


# --- Phase 2 Models ---

@dataclass
class ExecutionHistoryModel:
    id: Optional[int]
    repository_id: int
    execution_mode: str  # 'smart' or 'auto'
    status: str  # 'pending', 'analyzed', 'awaiting_approval', 'approved', 'rejected', 'committed', 'failed', 'invalidated'
    commit_hash: Optional[str]
    commit_message: Optional[str]
    created_at: str
    completed_at: Optional[str] = None
    error_summary: Optional[str] = None
    proposal_data: Optional[str] = None  # JSON serialized dictionary
    push_sync_status: Optional[str] = "LOCAL_ONLY"  # LOCAL_ONLY, PENDING_APPROVAL, READY_TO_PUSH, PUSHING, PUSHED, PUSH_FAILED, REMOTE_CONFLICT, VERIFICATION_FAILED
    branch_name: Optional[str] = None  # Branch this commit lives on (for push routing)
    local_commit_hash: Optional[str] = None
    remote_commit_hash: Optional[str] = None
    remote_advanced: bool = False
    verification_status: Optional[str] = None  # 'VERIFIED', 'FAILED', 'ADVANCED', 'SKIPPED'
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    remote_name: Optional[str] = None
    push_timestamp: Optional[str] = None
    push_error: Optional[str] = None


@dataclass
class ChangeGroupModel:
    id: Optional[int]
    execution_id: int
    group_name: str
    explanation: Optional[str]
    confidence: float
    file_list: List[str] = field(default_factory=list)


@dataclass
class ValidationResultModel:
    id: Optional[int]
    execution_id: int
    validation_type: str  # 'test', 'lint', 'build', 'secret', 'policy'
    status: str  # 'PASSED', 'FAILED', 'WARNING', 'SKIPPED'
    output_summary: Optional[str] = None
    duration: float = 0.0
    created_at: Optional[str] = None


@dataclass
class ExecutionApprovalModel:
    id: Optional[int]
    execution_id: int
    approval_status: str  # 'pending', 'approved', 'rejected'
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None  # 'user', 'cli', 'auto'
    notes: Optional[str] = None


@dataclass
class RepositoryAutomationSettingsModel:
    repository_id: int
    execution_mode: str = "smart"  # 'smart' or 'auto'
    auto_commit_enabled: bool = False  # MUST be False by default
    push_enabled: bool = False  # MUST be False by default
    protected_branches: List[str] = field(default_factory=lambda: ["main", "master"])
    validation_required: bool = True
    quiet_period_seconds: float = 3.0


# --- Phase 3 Models ---

@dataclass
class RepositoryPermissionModel:
    repository_id: int
    monitoring_enabled: bool = True
    ai_analysis_enabled: bool = True
    autonomous_development_enabled: bool = False  # MUST be False by default
    smart_commit_enabled: bool = True
    auto_commit_enabled: bool = False  # MUST be False by default
    remote_push_enabled: bool = False  # MUST be False by default
    updated_at: Optional[str] = None


@dataclass
class WeeklyScheduleModel:
    id: Optional[int]
    week_identifier: str  # e.g. "2026-W46"
    year: int
    week_number: int
    timezone: str
    is_active: bool = True
    created_at: str = ""


@dataclass
class ScheduledSessionModel:
    id: Optional[int]
    schedule_id: int
    scheduled_date: str  # YYYY-MM-DD
    day_of_week: int  # 0=Monday..6=Sunday
    time_window: str  # e.g. "14:00-16:00"
    status: str = "scheduled"  # 'scheduled', 'in_progress', 'completed', 'missed', 'skipped'
    executed_at: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class DevelopmentTaskModel:
    id: Optional[int]
    repository_id: int
    title: str
    description: Optional[str] = None
    task_type: str = "feature"  # 'feature', 'test', 'refactor', 'documentation', 'bugfix'
    status: str = "pending"  # 'pending', 'in_progress', 'completed', 'cancelled'
    priority: str = "medium"  # 'low', 'medium', 'high'
    created_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class ProjectContextModel:
    id: Optional[int]
    repository_id: int
    project_type: str
    primary_language: str
    framework: Optional[str] = None
    test_framework: Optional[str] = None
    summary: Optional[str] = None
    analyzed_at: str = ""


@dataclass
class DevelopmentSessionModel:
    id: Optional[int]
    repository_id: int
    session_date: str
    branch_name: str
    worktree_path: Optional[str] = None
    status: str = "running"  # 'running', 'completed', 'failed', 'no_op'
    tasks_summary: Optional[str] = None
    files_modified: List[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    created_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class DevelopmentChangeModel:
    id: Optional[int]
    session_id: int
    file_path: str
    change_type: str  # 'created', 'modified', 'deleted'
    description: Optional[str] = None
    diff_snippet: Optional[str] = None


# --- Phase 4 Models ---

@dataclass
class GitHubSyncHistoryModel:
    id: Optional[int]
    repository_id: int
    operation_type: str  # 'fetch', 'push'
    branch: str
    status: str  # 'success', 'failed', 'conflict', 'skipped'
    commit_hash: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    error_summary: Optional[str] = None


@dataclass
class RemoteRepositoryStatusModel:
    id: Optional[int]
    repository_id: int
    local_branch: str
    remote_branch: str
    ahead_count: int = 0
    behind_count: int = 0
    last_fetch_at: Optional[str] = None
    last_push_at: Optional[str] = None
    sync_status: str = "unknown"  # 'synced', 'ahead', 'behind', 'diverged', 'no_remote', 'unknown'


@dataclass
class NotificationModel:
    id: Optional[int]
    repository_id: Optional[int]
    notification_type: str  # 'commit', 'validation', 'secret', 'push', 'conflict', 'scheduler', 'service'
    title: str
    message: str
    severity: str = "info"  # 'info', 'success', 'warning', 'error'
    is_read: bool = False
    created_at: str = ""


@dataclass
class ApplicationServiceStatusModel:
    id: Optional[int]
    service_name: str
    status: str  # 'running', 'stopped', 'degraded', 'recovering'
    last_heartbeat: str = ""
    last_error: Optional[str] = None
    updated_at: str = ""


@dataclass
class DashboardPreferenceModel:
    id: Optional[int]
    preference_key: str
    preference_value: str
    updated_at: str = ""


@dataclass
class PullRequestModel:
    id: Optional[int]
    repository_id: int
    pr_number: int
    title: str
    source_branch: str
    target_branch: str
    state: str  # 'open', 'closed', 'merged', 'draft'
    html_url: str
    is_merged: bool = False
    created_at: str = ""
    updated_at: str = ""
    merged_at: Optional[str] = None
    body: Optional[str] = None
    diff_url: Optional[str] = None


