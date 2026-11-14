import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import { CommitRecord, Repository } from '../types';
import {
  GitCommit,
  Search,
  Filter,
  Eye,
  X,
  FileText,
  CheckCircle2,
  Upload,
  RefreshCw,
  AlertCircle,
  Clock,
  CloudOff,
  Cloud,
  Loader2,
} from 'lucide-react';

// ─── Push Sync Status Badge ───────────────────────────────────────────────────

type PushSyncStatus =
  | 'LOCAL_ONLY'
  | 'PENDING_APPROVAL'
  | 'READY_TO_PUSH'
  | 'PUSHING'
  | 'PUSHED'
  | 'PUSH_FAILED'
  | 'REMOTE_CONFLICT'
  | 'VERIFICATION_FAILED'
  | 'UNKNOWN'
  | undefined;

const SyncBadge: React.FC<{ syncStatus: PushSyncStatus; verificationStatus?: string | null }> = ({
  syncStatus,
  verificationStatus,
}) => {
  switch (syncStatus) {
    case 'PUSHED':
      return (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
          title={verificationStatus ? `Verified: ${verificationStatus}` : 'Verified on remote'}
        >
          <CheckCircle2 className="w-3 h-3" /> Pushed
        </span>
      );
    case 'PUSHING':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
          <Loader2 className="w-3 h-3 animate-spin" /> Pushing…
        </span>
      );
    case 'PUSH_FAILED':
      return (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400"
          title={verificationStatus ? `Error: ${verificationStatus}` : 'Push failed'}
        >
          <AlertCircle className="w-3 h-3" /> Push Failed
        </span>
      );
    case 'VERIFICATION_FAILED':
      return (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-400"
          title="Push command returned success but remote commit could not be verified"
        >
          <AlertCircle className="w-3 h-3" /> Verify Failed
        </span>
      );
    case 'PENDING_APPROVAL':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
          <Clock className="w-3 h-3" /> Pending
        </span>
      );
    case 'REMOTE_CONFLICT':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-400">
          <AlertCircle className="w-3 h-3" /> Conflict
        </span>
      );
    case 'READY_TO_PUSH':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400">
          <Cloud className="w-3 h-3" /> Ready
        </span>
      );
    case 'UNKNOWN':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
          <CloudOff className="w-3 h-3" /> Unverified
        </span>
      );
    case 'LOCAL_ONLY':
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          <CloudOff className="w-3 h-3" /> Local Only
        </span>
      );
  }
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export const CommitHistoryPage: React.FC = () => {
  const [commits, setCommits] = useState<CommitRecord[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repoPermissions, setRepoPermissions] = useState<Record<string | number, boolean>>({});
  const [selectedRepo, setSelectedRepo] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCommit, setSelectedCommit] = useState<CommitRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushingId, setPushingId] = useState<string | null>(null); // commit_hash being pushed
  const [pushError, setPushError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<Record<string | number, any>>({});
  const [confirmPushCommit, setConfirmPushCommit] = useState<CommitRecord | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setPushError(null);
    try {
      const repos = await api.getRepositories();
      setRepositories(repos);

      // Load permissions for each repo
      const permsMap: Record<string | number, boolean> = {};
      await Promise.all(
        repos.map(async (r: Repository) => {
          const rid = r.id ?? r.repo_id;
          if (rid == null) return;
          try {
            const perms = await api.getRepositoryPermissions(rid);
            permsMap[rid] = !!(perms?.remote_push_enabled ?? perms?.remote_push);
          } catch {
            permsMap[rid] = false;
          }
        })
      );
      setRepoPermissions(permsMap);

      // Build repoId filter from selected name
      let repoIdParam: string | undefined;
      if (selectedRepo !== 'all') {
        const found = repos.find(
          (r: Repository) => (r.repository_name || r.name) === selectedRepo
        );
        repoIdParam = found ? String(found.id ?? found.repo_id) : undefined;
      }

      // Load commits (with push_sync_status now returned by backend)
      const history = await api.getCommitHistory(repoIdParam ? selectedRepo : undefined, 100);

      // Normalize: map message → commit_message, date → timestamp, etc.
      const normalized = history.map((c: any) => ({
        ...c,
        commit_hash: c.commit_hash || c.hash,
        commit_message: c.commit_message || c.message || c.commit_message,
        repo_name: c.repo_name || c.repository_name,
        branch: c.branch,
        timestamp: c.timestamp || c.date || c.created_at,
        push_sync_status: c.push_sync_status as PushSyncStatus,
        execution_id: c.execution_id ?? null,
      }));

      setCommits(normalized);

      // Load remote sync status for selected repos
      const statusMap: Record<string | number, any> = {};
      const targetRepos =
        selectedRepo !== 'all'
          ? repos.filter((r: Repository) => (r.repository_name || r.name) === selectedRepo)
          : repos;
      await Promise.all(
        targetRepos.map(async (r: Repository) => {
          const rid = r.id ?? r.repo_id;
          if (rid == null) return;
          try {
            const s = await api.getRemoteStatus(rid);
            statusMap[rid] = s;
          } catch {
            /* ignore */
          }
        })
      );
      setSyncStatus(statusMap);
    } catch (err) {
      console.error('Failed to load commits', err);
    } finally {
      setLoading(false);
    }
  }, [selectedRepo]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filteredCommits = commits.filter((c) => {
    if (selectedRepo !== 'all') {
      const repoName = c.repo_name || c.repository_name || '';
      if (repoName !== selectedRepo) return false;
    }
    const q = searchQuery.toLowerCase();
    if (!q) return true;
    const msg = (c.commit_message || c.message || '').toLowerCase();
    const hash = (c.commit_hash || '').toLowerCase();
    const branch = (c.branch || '').toLowerCase();
    const repo = (c.repo_name || c.repository_name || '').toLowerCase();
    return msg.includes(q) || hash.includes(q) || branch.includes(q) || repo.includes(q);
  });

  const handlePush = async (commit: CommitRecord) => {
    const hash = commit.commit_hash || '';
    const repoId = commit.repository_id;
    setPushingId(hash);
    setPushError(null);

    try {
      if (commit.execution_id && repoId) {
        await api.pushCommit({
          repository_id: repoId,
          execution_id: commit.execution_id,
          commit_hash: commit.commit_hash || undefined,
          branch: commit.branch || undefined,
          target_branch: commit.target_branch || undefined,
          remote_name: commit.remote_name || 'origin',
        });
      } else if (repoId) {
        await api.pushCommit({
          repository_id: repoId,
          branch: commit.branch || undefined,
          remote_name: commit.remote_name || 'origin',
        });
      } else {
        throw new Error('Not enough information to push this commit.');
      }
      // Refresh after success
      await loadData();
    } catch (err: any) {
      setPushError(err.message || 'Push failed');
    } finally {
      setPushingId(null);
    }
  };

  const canPush = (commit: CommitRecord) => {
    const rid = commit.repository_id;
    if (rid == null) return false;
    return !!(repoPermissions[rid]);
  };

  const isPushable = (commit: CommitRecord) => {
    const st = commit.push_sync_status;
    return st === 'LOCAL_ONLY' || st === 'PUSH_FAILED' || st === 'READY_TO_PUSH' || st === 'VERIFICATION_FAILED' || st === 'UNKNOWN' || st == null;
  };

  // Build a summary of sync status for selected repos
  const selectedSyncStatuses = Object.values(syncStatus);
  const aheadTotal = selectedSyncStatuses.reduce((s, x) => s + (x?.ahead_count || 0), 0);
  const behindTotal = selectedSyncStatuses.reduce((s, x) => s + (x?.behind_count || 0), 0);
  const lastFetch = selectedSyncStatuses
    .map((x) => x?.last_fetch_at)
    .filter(Boolean)
    .sort()
    .reverse()[0];
  const lastPush = selectedSyncStatuses
    .map((x) => x?.last_push_at)
    .filter(Boolean)
    .sort()
    .reverse()[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Git Commit History</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Inspect autonomous and verified commits — push LOCAL_ONLY commits to GitHub.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Filter className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="pl-9 pr-8 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All Repositories</option>
              {repositories.map((r) => {
                const name = r.repository_name || r.name || `Repo ${r.id}`;
                const id = r.id ?? r.repo_id;
                return (
                  <option key={id} value={name}>
                    {name}
                  </option>
                );
              })}
            </select>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Sync Status Section */}
      {selectedSyncStatuses.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
          <h2 className="text-xs font-bold uppercase text-slate-400 mb-3">Sync Status</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-xs text-slate-400 block">Local Commits Ahead</span>
              <span className={`font-bold ${aheadTotal > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                {aheadTotal}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block">Remote Commits Behind</span>
              <span className={`font-bold ${behindTotal > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                {behindTotal}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block">Last Fetch</span>
              <span className="text-slate-700 dark:text-slate-300 text-xs">
                {lastFetch ? new Date(lastFetch).toLocaleString() : '—'}
              </span>
            </div>
            <div>
              <span className="text-xs text-slate-400 block">Last Push</span>
              <span className="text-slate-700 dark:text-slate-300 text-xs">
                {lastPush ? new Date(lastPush).toLocaleString() : '—'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Push error banner */}
      {pushError && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{pushError}</span>
          <button onClick={() => setPushError(null)} className="ml-auto p-0.5 hover:opacity-70">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search by commit message, hash, branch, or repository..."
          className="w-full pl-10 pr-4 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading commit records…</div>
        ) : filteredCommits.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <GitCommit className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="font-medium text-slate-600 dark:text-slate-300">No commits found</p>
            <p className="text-xs text-slate-400 mt-1">
              Commits created by AutoGit AI or detected in monitored repositories will show up here.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-6 py-3">Commit / Hash</th>
                  <th className="px-6 py-3">Repository & Branch</th>
                  <th className="px-6 py-3">Author</th>
                  <th className="px-6 py-3">Sync Status</th>
                  <th className="px-6 py-3">Timestamp</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {filteredCommits.map((c, idx) => {
                  const hash = c.commit_hash || '';
                  const isPushing = pushingId === hash;
                  const pushable = canPush(c) && isPushable(c);
                  const displayName = c.repo_name || c.repository_name || '—';
                  const displayMsg = c.commit_message || c.message || '(no message)';
                  const displayDate = c.timestamp || c.date || '';
                  const displayAuthor = c.author || 'AutoGit AI';

                  return (
                    <tr
                      key={`${hash}-${idx}`}
                      className="hover:bg-slate-50/70 dark:hover:bg-slate-700/30 transition-colors"
                    >
                      {/* Commit Hash & Message */}
                      <td className="px-6 py-4">
                        <div className="flex items-start gap-3">
                          <GitCommit className="w-4 h-4 text-primary-500 mt-1 shrink-0" />
                          <div>
                            <p className="font-medium text-slate-900 dark:text-slate-100 font-mono text-sm leading-snug max-w-xs truncate">
                              {displayMsg.split('\n')[0]}
                            </p>
                            <span className="inline-block px-1.5 py-0.5 mt-1 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded font-mono text-xs">
                              {hash.slice(0, 7) || 'N/A'}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Repo & Branch */}
                      <td className="px-6 py-4">
                        <span className="font-semibold text-slate-800 dark:text-slate-200">{displayName}</span>
                        <p className="text-xs text-slate-400 font-mono truncate max-w-[180px]">
                          refs/heads/{c.branch || 'main'}
                        </p>
                      </td>

                      {/* Author */}
                      <td className="px-6 py-4 text-xs text-slate-600 dark:text-slate-300">
                        {displayAuthor}
                      </td>

                      {/* Sync Status Badge */}
                      <td className="px-6 py-4">
                        <SyncBadge syncStatus={c.push_sync_status as PushSyncStatus} />
                      </td>

                      {/* Timestamp */}
                      <td className="px-6 py-4 text-xs text-slate-500">
                        {displayDate ? new Date(displayDate).toLocaleString() : '—'}
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {/* Push button */}
                          {pushable && (
                            <button
                              onClick={() => setConfirmPushCommit(c)}
                              disabled={isPushing}
                              className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
                              title="Push to GitHub"
                            >
                              {isPushing ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Upload className="w-3 h-3" />
                              )}
                              Push
                            </button>
                          )}
                          {/* Details button */}
                          <button
                            onClick={() => setSelectedCommit(c)}
                            className="inline-flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium px-2.5 py-1.5 rounded hover:bg-primary-50 dark:hover:bg-primary-950/40"
                          >
                            <Eye className="w-3.5 h-3.5" /> Details
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Push Confirmation Modal */}
      {confirmPushCommit && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full p-6 border border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Upload className="w-5 h-5 text-emerald-500" />
                Confirm GitHub Push
              </h3>
              <button
                onClick={() => setConfirmPushCommit(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <p className="text-slate-600 dark:text-slate-300">
                Are you sure you want to push this commit to the remote repository?
              </p>
              <div className="bg-slate-50 dark:bg-slate-900/50 p-4 rounded-lg space-y-2 border border-slate-200 dark:border-slate-700 font-mono text-xs">
                <div>
                  <span className="text-slate-500 dark:text-slate-400 font-sans font-semibold">Repository:</span>{' '}
                  <span className="text-slate-900 dark:text-slate-100 font-bold">{confirmPushCommit.repo_name || confirmPushCommit.repository_name || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400 font-sans font-semibold">Source Branch:</span>{' '}
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">{confirmPushCommit.source_branch || confirmPushCommit.branch || 'main'}</span>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400 font-sans font-semibold">Remote Name:</span>{' '}
                  <span className="text-slate-700 dark:text-slate-300">{confirmPushCommit.remote_name || 'origin'}</span>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400 font-sans font-semibold">Target Branch:</span>{' '}
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">{confirmPushCommit.target_branch || confirmPushCommit.source_branch || confirmPushCommit.branch || 'main'}</span>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400 font-sans font-semibold">Commit Hash:</span>{' '}
                  <span className="text-primary-600 dark:text-primary-400">{confirmPushCommit.commit_hash || 'HEAD'}</span>
                </div>
              </div>
              <p className="text-xs text-slate-500 italic">
                AutoGit AI will securely push using temporary credentials and verify that the commit is reachable on the remote branch before marking as pushed.
              </p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setConfirmPushCommit(null)}
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const target = confirmPushCommit;
                  setConfirmPushCommit(null);
                  handlePush(target);
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm flex items-center gap-2"
              >
                <Upload className="w-4 h-4" />
                Confirm & Push
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Slide-over details modal */}
      {selectedCommit && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-xl bg-white dark:bg-slate-800 h-full shadow-2xl p-6 overflow-y-auto border-l border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <GitCommit className="w-5 h-5 text-primary-500" />
                Commit Details
              </h3>
              <button
                onClick={() => setSelectedCommit(null)}
                className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-6 space-y-5">
              <div>
                <label className="text-xs uppercase font-bold text-slate-400">Full Message</label>
                <pre className="mt-1.5 p-3 rounded-lg bg-slate-50 dark:bg-slate-900 text-xs font-mono whitespace-pre-wrap text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800">
                  {selectedCommit.commit_message || selectedCommit.message}
                </pre>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-xs text-slate-400 block">Commit Hash</span>
                  <span className="font-mono text-xs text-slate-800 dark:text-slate-200 select-all">
                    {selectedCommit.commit_hash}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Repository</span>
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {selectedCommit.repo_name || selectedCommit.repository_name}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Branch</span>
                  <span className="font-mono text-xs text-slate-800 dark:text-slate-200">
                    {selectedCommit.branch}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Author</span>
                  <span className="text-xs text-slate-800 dark:text-slate-200">
                    {selectedCommit.author || 'AutoGit AI'}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Push Sync Status</span>
                  <SyncBadge syncStatus={selectedCommit.push_sync_status as PushSyncStatus} />
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Status</span>
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5" /> {selectedCommit.status || 'committed'}
                  </span>
                </div>
              </div>

              {selectedCommit.github_commit_url && (
                <div>
                  <span className="text-xs text-slate-400 block mb-1">GitHub Link</span>
                  <a
                    href={selectedCommit.github_commit_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary-600 dark:text-primary-400 underline break-all"
                  >
                    {selectedCommit.github_commit_url}
                  </a>
                </div>
              )}

              {selectedCommit.staged_files && selectedCommit.staged_files.length > 0 && (
                <div>
                  <label className="text-xs uppercase font-bold text-slate-400">
                    Committed Files ({selectedCommit.staged_files.length})
                  </label>
                  <div className="mt-2 space-y-1">
                    {selectedCommit.staged_files.map((file, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 p-2 rounded bg-slate-50 dark:bg-slate-900 text-xs font-mono text-slate-700 dark:text-slate-300"
                      >
                        <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                        <span className="truncate">{file}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Push action in detail panel */}
              {canPush(selectedCommit) && isPushable(selectedCommit) && (
                <div className="pt-2">
                  <button
                    onClick={() => {
                      handlePush(selectedCommit);
                      setSelectedCommit(null);
                    }}
                    disabled={pushingId === (selectedCommit.commit_hash || '')}
                    className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm disabled:opacity-60"
                  >
                    <Upload className="w-4 h-4" />
                    Push to GitHub
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
