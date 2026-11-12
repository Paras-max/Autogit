// ─────────────────────────────────────────────────────────────────────────────
// Unified API client for AutoGit AI frontend
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = '/api/v1';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) errorDetail = data.detail;
    } catch { /* ignore */ }
    throw new Error(errorDetail);
  }
  return res.json();
}

// ─── Repositories ─────────────────────────────────────────────────────────────
const getRepositories = () => fetchJSON<any[]>(`${API_BASE}/repositories`);

const addRepository = (path: string, name?: string) =>
  fetchJSON<any>(`${API_BASE}/repositories`, {
    method: 'POST',
    body: JSON.stringify({ path, name }),
  });

const removeRepository = (id: string | number) =>
  fetchJSON<any>(`${API_BASE}/repositories/${id}`, { method: 'DELETE' });

const getRepositoryPermissions = (repoId: string | number) =>
  fetchJSON<any>(`${API_BASE}/repositories/${repoId}/permissions`);

const updateRepositoryPermissions = (repoId: string | number, perms: Record<string, any>) =>
  fetchJSON<any>(`${API_BASE}/repositories/${repoId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify(perms),
  });

const enableDevelopment = (repoId: string | number) =>
  fetchJSON<any>(`${API_BASE}/repositories/${repoId}/permissions/enable-development`, { method: 'POST' });

const disableDevelopment = (repoId: string | number) =>
  fetchJSON<any>(`${API_BASE}/repositories/${repoId}/permissions/disable-development`, { method: 'POST' });

// ─── GitHub Sync & Remote Status ──────────────────────────────────────────────
const getGitHubAccount = () => fetchJSON<any>(`${API_BASE}/github/account`);

const disconnectGitHub = () =>
  fetchJSON<any>(`${API_BASE}/github/disconnect`, { method: 'POST' });

const getRemoteStatus = (repoId: string | number) =>
  fetchJSON<any>(`${API_BASE}/github/sync/status/${repoId}`);

const fetchRepository = (repoId: string | number) =>
  fetchJSON<any>(`${API_BASE}/github/sync/fetch/${repoId}`, { method: 'POST' });

const pushRepository = (repoId: string | number, branch?: string) =>
  fetchJSON<any>(`${API_BASE}/github/sync/push/${repoId}${branch ? `?branch=${branch}` : ''}`, { method: 'POST' });

// Legacy aliases kept for compatibility
const fetchRemote = fetchRepository;
const pushRemote = pushRepository;

const getSyncHistory = (repoId: string | number) =>
  fetchJSON<any[]>(`${API_BASE}/github/sync/history/${repoId}`);

// ─── Scheduler ────────────────────────────────────────────────────────────────
const getWeeklySchedule = () => fetchJSON<any>(`${API_BASE}/scheduler/weekly`);

const generateSchedule = (force = false) =>
  fetchJSON<any>(`${API_BASE}/scheduler/generate`, {
    method: 'POST',
    body: JSON.stringify({ force_regenerate: force }),
  });

const pauseScheduler = () =>
  fetchJSON<any>(`${API_BASE}/scheduler/pause`, { method: 'POST' });

const resumeScheduler = () =>
  fetchJSON<any>(`${API_BASE}/scheduler/resume`, { method: 'POST' });

// ─── Autonomous Development & Tasks ───────────────────────────────────────────
const getTasks = (repoId: string | number) =>
  fetchJSON<any[]>(`${API_BASE}/development/${repoId}/tasks`);

const addTask = (repoId: string | number, task: Record<string, any>) =>
  fetchJSON<any>(`${API_BASE}/development/${repoId}/tasks`, {
    method: 'POST',
    body: JSON.stringify(task),
  });

const deleteTask = (repoId: string | number, taskId: string | number) =>
  fetchJSON<any>(`${API_BASE}/development/${repoId}/tasks/${taskId}`, { method: 'DELETE' });

const runDevelopmentSession = (repoId: string | number, isolatedWorktree = true) =>
  fetchJSON<any>(`${API_BASE}/development/${repoId}/run`, {
    method: 'POST',
    body: JSON.stringify({ isolated_worktree: isolatedWorktree }),
  });

// ─── Commit Operations ────────────────────────────────────────────────────────
const getCommitHistory = (repoName?: string, limit = 50) =>
  fetchJSON<any[]>(`${API_BASE}/dashboard/commits${repoName ? `?repo_name=${encodeURIComponent(repoName)}&limit=${limit}` : `?limit=${limit}`}`);

const getCommitDetail = (hash: string) =>
  fetchJSON<any>(`${API_BASE}/dashboard/commits/${hash}`);

const getPendingApprovals = () =>
  fetchJSON<any[]>(`${API_BASE}/commits/pending`);

const approveCommit = (proposalId: string | number) =>
  fetchJSON<any>(`${API_BASE}/commits/${proposalId}/approve`, { method: 'POST' });

const rejectCommit = (proposalId: string | number) =>
  fetchJSON<any>(`${API_BASE}/commits/${proposalId}/reject`, { method: 'POST' });

const getExecutionHistory = (repoId?: string | number, limit = 50) =>
  fetchJSON<any[]>(`${API_BASE}/commits/history${repoId ? `?repository_id=${repoId}&limit=${limit}` : `?limit=${limit}`}`);

// Legacy alias
const getCommits = (repoId?: string | number) =>
  fetchJSON<any[]>(`${API_BASE}/dashboard/commits${repoId ? `?repository_id=${repoId}` : ''}`);

// ─── Dashboard & Analytics ────────────────────────────────────────────────────
const getDashboardOverview = () => fetchJSON<any>(`${API_BASE}/dashboard/overview`);

const getDashboardActivity = (limit = 50) =>
  fetchJSON<any[]>(`${API_BASE}/dashboard/activity?limit=${limit}`);

const getDashboardAgents = () =>
  fetchJSON<any>(`${API_BASE}/dashboard/agents`);

const getUpcomingSessions = () =>
  fetchJSON<any>(`${API_BASE}/dashboard/upcoming-sessions`);

// ─── Notifications ────────────────────────────────────────────────────────────
const getNotifications = (limit = 50, unreadOnly = false) =>
  fetchJSON<any[]>(`${API_BASE}/notifications?limit=${limit}${unreadOnly ? '&unread_only=true' : ''}`);

const markNotificationRead = (id: string | number) =>
  fetchJSON<any>(`${API_BASE}/notifications/${id}/read`, { method: 'POST' });

const markAllNotificationsRead = () =>
  fetchJSON<any>(`${API_BASE}/notifications/read-all`, { method: 'POST' });

// ─── Background Service & Health ──────────────────────────────────────────────
const getServiceHealth = () => fetchJSON<any>(`${API_BASE}/service/health`);

const getHealthStatus = () => fetchJSON<any>(`${API_BASE}/service/health`);

const getServiceStatus = () => fetchJSON<any>(`${API_BASE}/service/status`);

const serviceAction = (action: 'start' | 'stop' | 'restart') =>
  fetchJSON<any>(`${API_BASE}/service/${action}`, { method: 'POST' });

const startService = () => serviceAction('start');
const stopService = () => serviceAction('stop');
const restartService = () => serviceAction('restart');

// ─── Settings ─────────────────────────────────────────────────────────────────
const updateAISettings = (settings: Record<string, any>) =>
  fetchJSON<any>(`${API_BASE}/settings/ai`, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });

const updateGitIdentity = (identity: { name: string; email: string }) =>
  fetchJSON<any>(`${API_BASE}/settings/git-identity`, {
    method: 'PUT',
    body: JSON.stringify(identity),
  });

const getDashboardPreference = (key: string) =>
  fetchJSON<any>(`${API_BASE}/dashboard/preferences/${key}`);

const setDashboardPreference = (key: string, value: any) =>
  fetchJSON<any>(`${API_BASE}/dashboard/preferences/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  });

// ─── Unified api object (used by all pages) ───────────────────────────────────
export const api = {
  // Repositories
  getRepositories,
  addRepository,
  removeRepository,
  getRepositoryPermissions,
  updateRepositoryPermissions,
  enableDevelopment,
  disableDevelopment,
  // GitHub
  getGitHubAccount,
  disconnectGitHub,
  getRemoteStatus,
  fetchRepository,
  pushRepository,
  fetchRemote,
  pushRemote,
  getSyncHistory,
  // Scheduler
  getWeeklySchedule,
  generateSchedule,
  pauseScheduler,
  resumeScheduler,
  // Development
  getTasks,
  addTask,
  deleteTask,
  runDevelopmentSession,
  // Commits
  getCommitHistory,
  getCommitDetail,
  getPendingApprovals,
  approveCommit,
  rejectCommit,
  getExecutionHistory,
  getCommits,
  // Dashboard
  getDashboardOverview,
  getDashboardActivity,
  getDashboardAgents,
  getUpcomingSessions,
  // Notifications
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  // Service
  getServiceHealth,
  getHealthStatus,
  getServiceStatus,
  serviceAction,
  startService,
  stopService,
  restartService,
  // Settings
  updateAISettings,
  updateGitIdentity,
  getDashboardPreference,
  setDashboardPreference,
};

// Named exports for backward compatibility with existing pages
export {
  getRepositories, addRepository, removeRepository,
  getRepositoryPermissions, updateRepositoryPermissions,
  enableDevelopment, disableDevelopment,
  getGitHubAccount, disconnectGitHub,
  getRemoteStatus, fetchRemote, pushRemote, getSyncHistory,
  getWeeklySchedule, generateSchedule, pauseScheduler, resumeScheduler,
  getTasks, addTask, runDevelopmentSession,
  getDashboardOverview, getDashboardActivity, getDashboardAgents,
  getUpcomingSessions, getCommits, getCommitDetail,
  getNotifications, markNotificationRead, markAllNotificationsRead,
  getServiceHealth, getServiceStatus, startService, stopService,
};
