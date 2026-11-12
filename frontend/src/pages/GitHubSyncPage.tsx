import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { GitHubAccount, Repository } from '../types';
import {
  Github, RefreshCw, Upload, Download, AlertTriangle, CheckCircle2,
  XCircle, Clock, Zap, User, Star, GitFork, AlertCircle, Shield
} from 'lucide-react';

export const GitHubSyncPage: React.FC = () => {
  const [account, setAccount] = useState<GitHubAccount | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [syncStatus, setSyncStatus] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string, { type: 'success' | 'error' | 'warn'; text: string }>>({});

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

      const statuses: Record<string, any> = {};
      await Promise.all(
        repos.map(async (r) => {
          try {
            statuses[r.repo_id] = await api.getRemoteStatus(r.repo_id);
          } catch {
            statuses[r.repo_id] = null;
          }
        })
      );
      setSyncStatus(statuses);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFetch = async (repoId: string) => {
    setActionLoading((p) => ({ ...p, [`fetch_${repoId}`]: true }));
    setMessages((p) => ({ ...p, [repoId]: undefined! }));
    try {
      const res = await api.fetchRepository(repoId);
      setMessages((p) => ({ ...p, [repoId]: { type: 'success', text: res.message || 'Fetched successfully.' } }));
    } catch (err: any) {
      setMessages((p) => ({ ...p, [repoId]: { type: 'error', text: err?.message || 'Fetch failed.' } }));
    } finally {
      setActionLoading((p) => ({ ...p, [`fetch_${repoId}`]: false }));
    }
  };

  const handlePush = async (repoId: string) => {
    setActionLoading((p) => ({ ...p, [`push_${repoId}`]: true }));
    setMessages((p) => ({ ...p, [repoId]: undefined! }));
    try {
      const res = await api.pushRepository(repoId);
      setMessages((p) => ({ ...p, [repoId]: { type: 'success', text: res.message || 'Push succeeded.' } }));
    } catch (err: any) {
      setMessages((p) => ({ ...p, [repoId]: { type: 'error', text: err?.message || 'Push failed or not permitted.' } }));
    } finally {
      setActionLoading((p) => ({ ...p, [`push_${repoId}`]: false }));
    }
  };

  const rateLimitPct = account?.rate_limit_remaining != null && account?.rate_limit_limit != null
    ? Math.round((account.rate_limit_remaining / account.rate_limit_limit) * 100)
    : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">GitHub Sync</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Fetch and push authorized repositories. Push requires explicit <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">remote_push</code> permission per repository.
        </p>
      </div>

      {/* Account Card */}
      {account && (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-5 flex flex-col md:flex-row md:items-center gap-5">
          <img
            src={account.avatar_url || `https://github.com/${account.login}.png`}
            alt={account.login}
            className="w-14 h-14 rounded-full border-2 border-primary-400"
            onError={(e) => { (e.target as HTMLImageElement).src = 'https://github.com/ghost.png'; }}
          />
          <div className="flex-1 min-w-0">
            <p className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Github className="w-5 h-5 text-slate-600 dark:text-slate-400" />
              {account.name || account.login}
              <span className="text-sm font-normal text-slate-500 dark:text-slate-400">@{account.login}</span>
            </p>
            <div className="flex flex-wrap gap-4 mt-2 text-sm text-slate-600 dark:text-slate-300">
              <span className="flex items-center gap-1"><Star className="w-3.5 h-3.5 text-amber-400" /> {account.public_repos} repos</span>
              <span className="flex items-center gap-1"><GitFork className="w-3.5 h-3.5 text-primary-400" /> {account.followers} followers</span>
              <span className="flex items-center gap-1"><User className="w-3.5 h-3.5 text-emerald-400" /> {account.following} following</span>
            </div>
          </div>
          {rateLimitPct !== null && (
            <div className="flex flex-col items-center gap-1">
              <div className="relative w-16 h-16">
                <svg className="w-16 h-16 -rotate-90" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-slate-200 dark:text-slate-700" />
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeDasharray={`${rateLimitPct} ${100 - rateLimitPct}`} strokeLinecap="round"
                    className={rateLimitPct > 50 ? 'text-emerald-500' : rateLimitPct > 20 ? 'text-amber-500' : 'text-red-500'} />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-slate-200">{rateLimitPct}%</div>
              </div>
              <span className="text-xs text-slate-500">API Quota</span>
              <span className="text-xs text-slate-400">{account.rate_limit_remaining}/{account.rate_limit_limit}</span>
            </div>
          )}
          <div className="flex flex-col items-end gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium px-2.5 py-1 bg-emerald-50 dark:bg-emerald-950/40 rounded-full">
              <CheckCircle2 className="w-3.5 h-3.5" /> Connected
            </span>
            <button onClick={loadAll} className="text-xs text-slate-500 hover:text-primary-600 flex items-center gap-1">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>
        </div>
      )}

      {/* Sync Safety Notice */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800">
        <Shield className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
        <div className="text-sm text-amber-800 dark:text-amber-200">
          <span className="font-semibold">Safe-sync policy:</span> Fetch is always read-only and non-destructive.
          Push is blocked if validation fails, secrets are detected, or the repository does not have <code className="text-xs bg-amber-100 dark:bg-amber-900 px-1 rounded">remote_push</code> permission enabled.
          Merge and rebase are never executed automatically.
        </div>
      </div>

      {/* Repository Sync Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="font-semibold text-slate-900 dark:text-white">Repository Sync Status</h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading...</div>
        ) : repositories.length === 0 ? (
          <div className="p-8 text-center text-slate-400">No repositories registered.</div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
            {repositories.map((repo) => {
              const status = syncStatus[repo.repo_id];
              const msg = messages[repo.repo_id];
              const fetchLoading = actionLoading[`fetch_${repo.repo_id}`];
              const pushLoading = actionLoading[`push_${repo.repo_id}`];
              const canPush = repo.permissions?.remote_push;

              return (
                <div key={repo.repo_id} className="p-5 space-y-3">
                  <div className="flex flex-col md:flex-row md:items-center gap-3 justify-between">
                    <div>
                      <p className="font-semibold text-slate-900 dark:text-white">{repo.name}</p>
                      <p className="text-xs text-slate-400 font-mono truncate max-w-xs">{repo.path}</p>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      {status ? (
                        <>
                          <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${
                            status.sync_status === 'up_to_date' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' :
                            status.sync_status === 'ahead' ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300' :
                            status.sync_status === 'behind' ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' :
                            'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
                          }`}>
                            {status.sync_status === 'up_to_date' && <CheckCircle2 className="w-3.5 h-3.5" />}
                            {status.sync_status === 'ahead' && <Upload className="w-3.5 h-3.5" />}
                            {status.sync_status === 'behind' && <Download className="w-3.5 h-3.5" />}
                            {status.sync_status === 'diverged' && <AlertTriangle className="w-3.5 h-3.5" />}
                            {status.sync_status?.replace(/_/g, ' ')}
                          </span>
                          {status.ahead_count > 0 && (
                            <span className="text-xs text-blue-600 dark:text-blue-400 font-mono">↑{status.ahead_count} commits ahead</span>
                          )}
                          {status.behind_count > 0 && (
                            <span className="text-xs text-amber-600 dark:text-amber-400 font-mono">↓{status.behind_count} commits behind</span>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" /> No remote data
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleFetch(repo.repo_id)}
                        disabled={fetchLoading}
                        className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-primary-50 hover:text-primary-700 dark:hover:bg-primary-950/40 dark:hover:text-primary-300 disabled:opacity-50 transition-colors"
                      >
                        <Download className={`w-3.5 h-3.5 ${fetchLoading ? 'animate-bounce' : ''}`} />
                        {fetchLoading ? 'Fetching…' : 'Fetch'}
                      </button>
                      <button
                        onClick={() => handlePush(repo.repo_id)}
                        disabled={pushLoading || !canPush}
                        title={canPush ? 'Push to remote' : 'Enable remote_push permission first'}
                        className={`inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                          canPush
                            ? 'bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50'
                            : 'bg-slate-100 dark:bg-slate-700 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                        }`}
                      >
                        <Upload className={`w-3.5 h-3.5 ${pushLoading ? 'animate-bounce' : ''}`} />
                        {pushLoading ? 'Pushing…' : 'Push'}
                        {!canPush && <Shield className="w-3 h-3 text-slate-400" />}
                      </button>
                    </div>
                  </div>
                  {msg && (
                    <div className={`flex items-start gap-2 text-xs p-3 rounded-lg ${
                      msg.type === 'success' ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300' :
                      msg.type === 'warn' ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300' :
                      'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300'
                    }`}>
                      {msg.type === 'success' ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> :
                       msg.type === 'warn' ? <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> :
                       <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
                      {msg.text}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
