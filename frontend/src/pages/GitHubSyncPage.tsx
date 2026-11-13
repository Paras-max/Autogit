import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { GitHubAccount, RemoteGitHubRepo, Repository } from '../types';
import {
  Github, RefreshCw, Upload, Download, AlertTriangle, CheckCircle2,
  XCircle, Clock, Star, GitFork, User, Shield, ExternalLink,
  Lock, Globe, FolderGit2, AlertCircle, Plus
} from 'lucide-react';

interface SyncMessage {
  type: 'success' | 'error' | 'warn';
  text: string;
}

export const GitHubSyncPage: React.FC = () => {
  const [account, setAccount] = useState<GitHubAccount | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [remoteRepos, setRemoteRepos] = useState<RemoteGitHubRepo[]>([]);
  const [syncStatus, setSyncStatus] = useState<Record<string | number, any>>({});
  const [loading, setLoading] = useState(true);
  const [loadingRemoteRepos, setLoadingRemoteRepos] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string | number, SyncMessage>>({});
  const [activeSubTab, setActiveSubTab] = useState<'sync' | 'remote_repos'>('sync');

  // Quick register local path modal
  const [registerModal, setRegisterModal] = useState<{ isOpen: boolean; repoName: string; cloneUrl: string }>({
    isOpen: false,
    repoName: '',
    cloneUrl: '',
  });
  const [localPathInput, setLocalPathInput] = useState('');
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [acc, repos] = await Promise.all([
        api.getGitHubAccount(),
        api.getRepositories(),
      ]);
      setAccount(acc);
      setRepositories(repos);

      // Load remote status for each registered repository
      const statuses: Record<string | number, any> = {};
      await Promise.all(
        repos.map(async (r) => {
          const repoId = r.id ?? r.repo_id;
          if (repoId != null) {
            try {
              statuses[repoId] = await api.getRemoteStatus(repoId);
            } catch {
              statuses[repoId] = null;
            }
          }
        })
      );
      setSyncStatus(statuses);

      // Fetch remote repos if account is authenticated
      if (acc && acc.authenticated) {
        loadRemoteRepos();
      }
    } catch (err) {
      console.error('Failed to load GitHub sync state:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRemoteRepos = async () => {
    setLoadingRemoteRepos(true);
    try {
      const remotes = await api.getGitHubRepositories(100);
      setRemoteRepos(Array.isArray(remotes) ? remotes : []);
    } catch (err) {
      console.error('Failed to list remote GitHub repositories:', err);
      setRemoteRepos([]);
    } finally {
      setLoadingRemoteRepos(false);
    }
  };

  const handleFetch = async (repoId: string | number) => {
    setActionLoading((p) => ({ ...p, [`fetch_${repoId}`]: true }));
    setMessages((p) => {
      const copy = { ...p };
      delete copy[repoId];
      return copy;
    });
    try {
      const res = await api.fetchRepository(repoId);
      setMessages((p) => ({ ...p, [repoId]: { type: 'success' as const, text: res.message || 'Fetched successfully without modifying working tree.' } }));
      // Refresh status
      const updated = await api.getRemoteStatus(repoId);
      setSyncStatus((p) => ({ ...p, [repoId]: updated }));
    } catch (err: any) {
      setMessages((p) => ({ ...p, [repoId]: { type: 'error' as const, text: err?.message || 'Fetch failed.' } }));
    } finally {
      setActionLoading((p) => ({ ...p, [`fetch_${repoId}`]: false }));
    }
  };

  const handlePush = async (repoId: string | number) => {
    setActionLoading((p) => ({ ...p, [`push_${repoId}`]: true }));
    setMessages((p) => {
      const copy = { ...p };
      delete copy[repoId];
      return copy;
    });
    try {
      const res = await api.pushRepository(repoId);
      setMessages((p) => ({ ...p, [repoId]: { type: 'success' as const, text: res.message || 'Push completed successfully.' } }));
      const updated = await api.getRemoteStatus(repoId);
      setSyncStatus((p) => ({ ...p, [repoId]: updated }));
    } catch (err: any) {
      setMessages((p) => ({ ...p, [repoId]: { type: 'error' as const, text: err?.message || 'Push rejected. Check remote_push permissions and secret scan.' } }));
    } finally {
      setActionLoading((p) => ({ ...p, [`push_${repoId}`]: false }));
    }
  };

  const handleRegisterLocal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localPathInput.trim()) return;
    setRegistering(true);
    setRegisterError(null);
    try {
      await api.addRepository(localPathInput.trim(), registerModal.repoName);
      setRegisterModal({ isOpen: false, repoName: '', cloneUrl: '' });
      setLocalPathInput('');
      await loadAll();
    } catch (err: any) {
      setRegisterError(err?.message || 'Failed to register local repository');
    } finally {
      setRegistering(false);
    }
  };

  // Extract authenticated user profile
  const isAuthenticated = Boolean(account && account.authenticated);
  const user = account?.user || (account?.login ? account : null);
  const rateLimit = account?.rate_limit || {
    limit: account?.rate_limit_limit ?? 5000,
    remaining: account?.rate_limit_remaining ?? 5000,
    reset: account?.rate_limit_reset ?? 0,
  };
  const rateLimitPct = rateLimit.limit > 0
    ? Math.round((rateLimit.remaining / rateLimit.limit) * 100)
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Github className="w-6 h-6 text-slate-700 dark:text-slate-300" />
            GitHub Synchronization & Accounts
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Real GitHub authentication via Fine-grained Personal Access Token. Fetch and push operations strictly enforce per-repository permissions.
          </p>
        </div>
        <button
          onClick={loadAll}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-600 dark:text-slate-300 hover:text-primary-600 transition-colors self-start md:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Status
        </button>
      </div>

      {/* Account Card */}
      {loading ? (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-8 text-center text-slate-500 text-sm">
          Validating GitHub credentials and inspecting account profile...
        </div>
      ) : isAuthenticated && user ? (
        /* Genuine Authenticated Profile */
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 flex flex-col md:flex-row md:items-center gap-6">
          <div className="relative">
            <img
              src={user.avatar_url || `https://github.com/${user.login}.png`}
              alt={user.login || 'GitHub User'}
              className="w-16 h-16 rounded-full border-2 border-emerald-500 shadow-sm"
              onError={(e) => {
                (e.target as HTMLImageElement).src = `https://github.com/${user.login}.png`;
              }}
            />
            <span className="absolute bottom-0 right-0 w-4 h-4 rounded-full bg-emerald-500 border-2 border-white dark:border-slate-800" title="Token Valid" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                {user.name || user.login}
              </h2>
              <a
                href={user.html_url || `https://github.com/${user.login}`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-primary-600 dark:text-primary-400 font-mono hover:underline inline-flex items-center gap-0.5"
              >
                @{user.login}
                <ExternalLink className="w-3 h-3" />
              </a>
              {user.id && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500">
                  ID: {user.id}
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-4 mt-2 text-xs text-slate-600 dark:text-slate-300">
              <span className="flex items-center gap-1 font-medium">
                <Star className="w-3.5 h-3.5 text-amber-500" />
                {user.public_repos ?? 0} public repos
              </span>
              {(user.total_private_repos ?? 0) > 0 && (
                <span className="flex items-center gap-1 font-medium">
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  {user.total_private_repos} private repos
                </span>
              )}
              {account?.token_preview && (
                <span className="font-mono text-slate-400 bg-slate-100 dark:bg-slate-700/60 px-2 py-0.5 rounded">
                  Token: {account.token_preview}
                </span>
              )}
            </div>
          </div>

          {/* Rate Limit Meter */}
          {rateLimitPct !== null && (
            <div className="flex flex-col items-center gap-1 shrink-0 px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="text-xs font-semibold text-slate-600 dark:text-slate-400">GitHub API Quota</div>
              <div className="text-lg font-bold text-slate-900 dark:text-white font-mono">
                {rateLimit.remaining} <span className="text-xs font-normal text-slate-400">/ {rateLimit.limit}</span>
              </div>
              <div className="w-28 bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 mt-1 overflow-hidden">
                <div
                  className={`h-1.5 rounded-full ${
                    rateLimitPct > 50 ? 'bg-emerald-500' : rateLimitPct > 20 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${rateLimitPct}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex flex-col items-end gap-2 shrink-0">
            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300 font-semibold px-3 py-1 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 rounded-full">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              Authenticated
            </span>
          </div>
        </div>
      ) : (
        /* Genuine Unauthenticated or Error Card */
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-bold text-amber-900 dark:text-amber-200">
                GitHub Token Unconfigured or Invalid
              </p>
              <p className="text-xs text-amber-800 dark:text-amber-300 mt-1 leading-relaxed">
                {account?.error || 'No valid GitHub token detected in .env. Configure GITHUB_TOKEN=github_pat_... to enable repository synchronization and remote inspection.'}
              </p>
            </div>
          </div>
          <button
            onClick={loadAll}
            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-medium shrink-0 transition-colors"
          >
            Retry Validation
          </button>
        </div>
      )}

      {/* Safety Policy Notice */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
        <Shield className="w-5 h-5 text-primary-500 mt-0.5 shrink-0" />
        <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          <span className="font-semibold text-slate-800 dark:text-slate-100">Safe Synchronization Guarantees:</span>{' '}
          Fetch is completely non-destructive (uses remote tracking branches only without touching your working directory).
          Push is blocked by default and requires explicit <code className="bg-slate-200 dark:bg-slate-700 px-1 py-0.5 rounded font-mono text-[11px]">remote_push</code> permission per repository, alongside automated secret and conflict validation checks. Force-push is strictly prohibited.
        </div>
      </div>

      {/* Navigation Sub-tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-700 pb-2">
        <button
          onClick={() => setActiveSubTab('sync')}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeSubTab === 'sync'
              ? 'bg-primary-600 text-white shadow-sm'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          <FolderGit2 className="w-4 h-4" />
          Registered Local Repositories ({repositories.length})
        </button>
        <button
          onClick={() => {
            setActiveSubTab('remote_repos');
            if (remoteRepos.length === 0 && isAuthenticated) loadRemoteRepos();
          }}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeSubTab === 'remote_repos'
              ? 'bg-primary-600 text-white shadow-sm'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          <Globe className="w-4 h-4" />
          Authorized Remote Repositories ({remoteRepos.length})
        </button>
      </div>

      {/* Tab 1: Local Monitored Repositories & Sync Controls */}
      {activeSubTab === 'sync' && (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <h2 className="font-semibold text-sm text-slate-900 dark:text-white flex items-center gap-2">
              <FolderGit2 className="w-4 h-4 text-primary-500" />
              Monitored Repository Synchronization Status
            </h2>
            <span className="text-xs text-slate-400">
              {repositories.length} repository registered
            </span>
          </div>

          {repositories.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <FolderGit2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium text-slate-600 dark:text-slate-300">No local repositories registered</p>
              <p className="text-xs text-slate-400 mt-1">
                Go to the Repositories tab to add a local Git folder or import one from your authorized remote repositories.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
              {repositories.map((repo) => {
                const repoId = repo.id ?? repo.repo_id;
                const repoName = repo.repository_name || repo.name || 'Unnamed Repository';
                const repoPath = repo.repository_path || repo.path || '';
                const status = syncStatus[repoId];
                const msg = messages[repoId];
                const fetchLoading = actionLoading[`fetch_${repoId}`];
                const pushLoading = actionLoading[`push_${repoId}`];
                const canPush = Boolean(repo.permissions?.remote_push_enabled || repo.permissions?.remote_push);

                return (
                  <div key={repoId} className="p-5 space-y-3">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-semibold text-sm text-slate-900 dark:text-white">{repoName}</p>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500">
                            ID: {repoId}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 font-mono truncate max-w-md mt-0.5" title={repoPath}>
                          {repoPath}
                        </p>
                        {repo.remote_url && (
                          <p className="text-[11px] text-primary-600 dark:text-primary-400 font-mono truncate max-w-md mt-0.5">
                            Remote: {repo.remote_url}
                          </p>
                        )}
                      </div>

                      {/* Sync Status Badge */}
                      <div className="flex items-center gap-3 flex-wrap">
                        {status ? (
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${
                              status.sync_status === 'up_to_date' || status.sync_status === 'synced'
                                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                                : status.sync_status === 'ahead'
                                ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                                : status.sync_status === 'behind'
                                ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                                : status.sync_status === 'no_remote'
                                ? 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                                : 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border border-red-200 dark:border-red-800'
                            }`}>
                              {status.sync_status === 'up_to_date' || status.sync_status === 'synced' ? <CheckCircle2 className="w-3.5 h-3.5" /> : null}
                              {status.sync_status === 'ahead' && <Upload className="w-3.5 h-3.5" />}
                              {status.sync_status === 'behind' && <Download className="w-3.5 h-3.5" />}
                              {status.sync_status === 'diverged' && <AlertTriangle className="w-3.5 h-3.5" />}
                              {status.sync_status?.replace(/_/g, ' ').toUpperCase()}
                            </span>

                            {status.ahead_count > 0 && (
                              <span className="text-xs text-blue-600 dark:text-blue-400 font-mono font-medium">
                                ↑{status.ahead_count} ahead
                              </span>
                            )}
                            {status.behind_count > 0 && (
                              <span className="text-xs text-amber-600 dark:text-amber-400 font-mono font-medium">
                                ↓{status.behind_count} behind
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400 flex items-center gap-1 font-mono">
                            <Clock className="w-3.5 h-3.5" /> No remote data
                          </span>
                        )}
                      </div>

                      {/* Action Buttons */}
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => handleFetch(repoId)}
                          disabled={fetchLoading}
                          className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50 transition-colors"
                        >
                          <Download className={`w-3.5 h-3.5 ${fetchLoading ? 'animate-bounce' : ''}`} />
                          {fetchLoading ? 'Fetching...' : 'Fetch'}
                        </button>
                        <button
                          onClick={() => handlePush(repoId)}
                          disabled={pushLoading || !canPush}
                          title={canPush ? 'Push commits to remote' : 'Permission remote_push is DISABLED for this repository'}
                          className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${
                            canPush
                              ? 'bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-400 border border-slate-200 dark:border-slate-700 cursor-not-allowed'
                          }`}
                        >
                          <Upload className={`w-3.5 h-3.5 ${pushLoading ? 'animate-bounce' : ''}`} />
                          {pushLoading ? 'Pushing...' : 'Push'}
                          {!canPush && <Shield className="w-3 h-3 text-slate-400" />}
                        </button>
                      </div>
                    </div>

                    {msg && (
                      <div className={`flex items-start gap-2 text-xs p-3 rounded-lg ${
                        msg.type === 'success'
                          ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                          : msg.type === 'warn'
                          ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                          : 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
                      }`}>
                        {msg.type === 'success' ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" /> : <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
                        <span>{msg.text}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Authorized Remote GitHub Repositories */}
      {activeSubTab === 'remote_repos' && (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                <Globe className="w-4 h-4 text-primary-500" />
                Authorized GitHub Repositories for @{user?.login || 'User'}
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Repositories accessible under your configured Personal Access Token. Match or register a local clone to begin autonomous monitoring.
              </p>
            </div>
            <button
              onClick={loadRemoteRepos}
              disabled={loadingRemoteRepos}
              className="text-xs text-slate-500 hover:text-primary-600 flex items-center gap-1 font-medium"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingRemoteRepos ? 'animate-spin' : ''}`} />
              Reload
            </button>
          </div>

          {loadingRemoteRepos ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              Querying GitHub API for authorized repositories...
            </div>
          ) : remoteRepos.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <Github className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium text-slate-600 dark:text-slate-300">No remote repositories found</p>
              <p className="text-xs text-slate-400 mt-1">
                Ensure your Personal Access Token has repository read scopes (repo or read:user).
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
              {remoteRepos.map((r) => {
                // Check if already registered locally by matching remote URL or name
                const matchedLocal = repositories.find(
                  (lr) =>
                    (lr.remote_url && lr.remote_url.toLowerCase().includes(r.name.toLowerCase())) ||
                    (lr.repository_name && lr.repository_name.toLowerCase() === r.name.toLowerCase())
                );

                return (
                  <div key={r.id || r.full_name} className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <a
                          href={r.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold text-sm text-slate-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400 hover:underline flex items-center gap-1"
                        >
                          {r.full_name}
                          <ExternalLink className="w-3 h-3 text-slate-400" />
                        </a>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          r.private
                            ? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
                            : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                        }`}>
                          {r.private ? 'Private' : 'Public'}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          branch: {r.default_branch}
                        </span>
                      </div>

                      {r.description && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-1">
                          {r.description}
                        </p>
                      )}

                      <p className="text-[11px] text-slate-400 font-mono mt-1 select-all">
                        {r.clone_url}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {matchedLocal ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Registered (ID: {matchedLocal.id ?? matchedLocal.repo_id})
                        </span>
                      ) : (
                        <button
                          onClick={() => {
                            setRegisterModal({
                              isOpen: true,
                              repoName: r.name,
                              cloneUrl: r.clone_url,
                            });
                            setLocalPathInput('');
                            setRegisterError(null);
                          }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold transition-colors"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Register Local Clone
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Modal: Register Local Clone */}
      {registerModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 dark:border-slate-700 space-y-4">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <FolderGit2 className="w-5 h-5 text-primary-500" />
              Register Local Copy of {registerModal.repoName}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Enter the local filesystem path on your machine where this repository is cloned. AutoGit AI will monitor it and allow controlled synchronization with GitHub.
            </p>

            <form onSubmit={handleRegisterLocal} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  Local Folder Path
                </label>
                <input
                  type="text"
                  placeholder="e.g. C:/Users/YourName/Projects/my-repo"
                  value={localPathInput}
                  onChange={(e) => setLocalPathInput(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono"
                  autoFocus
                />
              </div>

              {registerError && (
                <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{registerError}</span>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setRegisterModal({ isOpen: false, repoName: '', cloneUrl: '' })}
                  className="px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={registering || !localPathInput.trim()}
                  className="px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold disabled:opacity-50 transition-colors"
                >
                  {registering ? 'Registering...' : 'Register Repository'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
