// ─────────────────────────────────────────────────────────────────────────────
// AutoGit AI – Shared TypeScript interfaces
// ─────────────────────────────────────────────────────────────────────────────

export interface Repository {
  // Core fields (Phase 1 / Phase 3 schema)
  id?: number;
  repo_id: string;
  name: string;
  path: string;
  description?: string | null;
  remote_url?: string | null;
  current_branch?: string | null;
  created_at?: string;
  // Alias fields returned by some endpoints
  repository_name?: string;
  repository_path?: string;
  permissions?: RepositoryPermissions;
}

export interface RepositoryPermissions {
  repository_id?: number | string;
  repo_id?: string;
  monitoring_enabled?: boolean;
  ai_analysis_enabled?: boolean;
  autonomous_development_enabled?: boolean;
  smart_commit_enabled?: boolean;
  auto_commit_enabled?: boolean;
  remote_push?: boolean;
  remote_push_enabled?: boolean;
  pull_request_creation_enabled?: boolean;
  updated_at?: string | null;
  [key: string]: any;
}

export interface RemoteStatus {
  repository_id?: number | string;
  local_branch?: string;
  remote_branch?: string;
  tracking_branch?: string | null;
  ahead_count: number;
  behind_count: number;
  sync_status: 'up_to_date' | 'synced' | 'ahead' | 'behind' | 'diverged' | 'no_remote' | 'unknown';
  last_fetch_at?: string | null;
  last_push_at?: string | null;
  has_conflicts?: boolean;
}

export interface CommitRecord {
  commit_hash?: string | null;
  commit_message?: string | null;
  repo_name?: string | null;
  branch?: string | null;
  staged_files?: string[];
  status?: string;
  timestamp?: string;
  // Legacy fields
  short_hash?: string;
  message?: string;
  author?: string;
  date?: string;
  repository_id?: number;
  repository_name?: string;
  github_commit_url?: string | null;
  // Push sync state machine
  push_sync_status?: 'LOCAL_ONLY' | 'PENDING_APPROVAL' | 'READY_TO_PUSH' | 'PUSHING' | 'PUSHED' | 'PUSH_FAILED' | 'REMOTE_CONFLICT' | 'VERIFICATION_FAILED' | 'UNKNOWN';
  execution_id?: number | null;
  source_branch?: string | null;
  target_branch?: string | null;
  remote_name?: string | null;
  verification_status?: string | null;
  remote_advanced?: boolean;
  local_commit_hash?: string | null;
  remote_commit_hash?: string | null;
  push_timestamp?: string | null;
  push_error?: string | null;
}

// Legacy alias kept for compatibility
export type CommitItem = CommitRecord;

export interface Notification {
  notification_id: string;
  id?: number | string;
  repo_name?: string | null;
  repository_id?: number | null;
  notification_type?: string;
  kind?: string;
  title: string;
  message: string;
  severity?: 'info' | 'success' | 'warning' | 'error';
  read?: boolean;
  is_read?: boolean;
  created_at?: string;
}

// Legacy alias
export type NotificationItem = Notification;

export interface ScheduledSession {
  id?: number;
  schedule_id?: number;
  scheduled_date: string;
  day_of_week?: number;
  time_window?: string;
  status: 'scheduled' | 'in_progress' | 'completed' | 'missed' | 'skipped';
  executed_at?: string | null;
  notes?: string | null;
}

export interface WeeklySchedule {
  id?: number;
  week_identifier?: string;
  year?: number;
  week_number?: number;
  timezone?: string;
  is_active?: boolean;
  created_at?: string;
  sessions: ScheduledSession[];
}

export interface DevelopmentTask {
  id?: number;
  task_id?: string;
  repository_id?: number | string;
  title: string;
  description?: string | null;
  task_type: 'feature' | 'test' | 'refactor' | 'documentation' | 'bugfix';
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  priority: 'low' | 'medium' | 'high';
  created_at?: string;
  completed_at?: string | null;
}

export interface DashboardOverview {
  total_repositories?: number;
  authorized_repositories?: number;
  active_sessions?: number;
  total_commits?: number;
  pending_approvals?: number;
  validation_failures?: number;
  monitoring_active?: boolean;
  scheduler_active?: boolean;
  current_week?: string;
  agents_online?: number;
  [key: string]: any;
}

export interface DashboardActivity {
  id?: string;
  event_type?: string;
  type?: string;
  repository_id?: number | null;
  repository_name?: string | null;
  repo_name?: string | null;
  title?: string;
  description?: string;
  message?: string;
  timestamp?: string;
  created_at?: string;
  status?: string;
}

export interface AIAgentInfo {
  name: string;
  role: string;
  status: 'online' | 'active' | 'idle' | 'error';
  description?: string;
  last_run?: string | null;
}

export interface RemoteGitHubRepo {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  clone_url: string;
  ssh_url?: string;
  default_branch: string;
  description?: string | null;
  updated_at?: string;
  pushed_at?: string;
}

export interface GitHubAccount {
  id?: number;
  login?: string;
  name?: string | null;
  avatar_url?: string | null;
  html_url?: string | null;
  public_repos?: number;
  total_private_repos?: number;
  followers?: number;
  following?: number;
  rate_limit_limit?: number;
  rate_limit_remaining?: number;
  rate_limit_reset?: number;
  token_preview?: string | null;
  status?: string;
  authenticated?: boolean;
  error?: string | null;
  user?: {
    id?: number;
    login: string;
    name?: string | null;
    avatar_url?: string | null;
    html_url?: string | null;
    public_repos?: number;
    total_private_repos?: number;
    followers?: number;
    following?: number;
  } | null;
  rate_limit?: {
    limit: number;
    remaining: number;
    reset: number;
  } | null;
}

// Legacy alias
export type GitHubAccountInfo = GitHubAccount;

export interface ServiceHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  uptime_seconds?: number;
  uptime?: string;
  timestamp?: string;
  pid?: number;
  database?: { connected: boolean; error?: string | null };
  scheduler?: { active: boolean; timezone: string };
  monitoring?: { active_observers: number };
  checks?: Record<string, any>;
  [key: string]: any;
}

export interface AdditionalCommitItem {
  commit_hash: string;
  short_hash: string;
  commit_message: string;
  author?: string;
  date?: string;
}

export interface PushPreviewResponse {
  repository_id: number;
  source_branch: string;
  target_branch: string;
  remote_name: string;
  selected_commit_hash: string;
  selected_commit_message?: string;
  branch_head_hash: string;
  is_branch_head: boolean;
  has_additional_commits: boolean;
  additional_commits_count: number;
  additional_commits: AdditionalCommitItem[];
  total_commits_to_push_count: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 4 Step 4: Pull Request Types
// ─────────────────────────────────────────────────────────────────────────────

export interface PullRequestItem {
  id?: number;
  repository_id: number;
  pr_number: number;
  github_pr_id?: number | null;
  title: string;
  body?: string | null;
  source_branch: string;
  target_branch: string;
  state: 'open' | 'closed' | 'merged' | 'draft' | 'review_pending' | 'changes_requested' | string;
  is_draft: boolean;
  is_merged: boolean;
  html_url: string;
  diff_url?: string | null;
  head_commit_sha?: string | null;
  base_commit_sha?: string | null;
  created_at: string;
  updated_at: string;
  merged_at?: string | null;
  last_synced_at?: string | null;
  last_sync_error?: string | null;
}

export interface BranchItem {
  name: string;
  is_remote: boolean;
  is_current: boolean;
  commit_hash?: string | null;
  commit_message?: string | null;
}

export interface RepositoryBranches {
  repository_id: number;
  default_branch: string;
  local_branches: BranchItem[];
  remote_branches: BranchItem[];
}

export interface CommitComparisonItem {
  sha: string;
  short_sha: string;
  message: string;
  author?: string | null;
  date?: string | null;
}

export interface FileComparisonItem {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  patch?: string | null;
}

export interface ValidationCheckItem {
  name: string;
  status: 'PASSED' | 'FAILED' | 'WARNING' | 'NOT_CONFIGURED' | 'NOT_RUN' | string;
  message?: string | null;
  details?: Record<string, any> | null;
}

export interface PRValidationSummary {
  overall_status: 'PASSED' | 'FAILED' | 'WARNING' | string;
  can_create: boolean;
  blocking_reasons: string[];
  checks: ValidationCheckItem[];
}

export interface PullRequestPrepareResponse {
  repository_id: number;
  source_branch: string;
  target_branch: string;
  is_pushed: boolean;
  ahead_count: number;
  behind_count: number;
  total_commits: number;
  commits: CommitComparisonItem[];
  changed_files_count: number;
  changed_files: FileComparisonItem[];
  additions: number;
  deletions: number;
  validation: PRValidationSummary;
  suggested_title: string;
  suggested_body: string;
  existing_pr_id?: number | null;
  existing_pr_number?: number | null;
  existing_pr_url?: string | null;
  can_create: boolean;
  blocking_reasons: string[];
}

export interface PullRequestCreateRequest {
  source_branch: string;
  target_branch: string;
  title: string;
  description?: string;
  is_draft?: boolean;
}

export interface PullRequestSyncResponse {
  repository_id: number;
  synced_count: number;
  prs: PullRequestItem[];
  error?: string | null;
}
