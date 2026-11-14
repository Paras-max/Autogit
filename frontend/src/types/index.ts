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
