import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import {
  PullRequestItem,
  PullRequestPrepareResponse,
  Repository,
  RepositoryBranches,
} from '../types';
import {
  GitPullRequest,
  Search,
  Filter,
  Eye,
  X,
  FileText,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
  AlertTriangle,
  Clock,
  ExternalLink,
  Loader2,
  Plus,
  GitBranch,
  ShieldCheck,
  FolderGit2,
  ChevronRight,
  GitCommit,
  Check,
} from 'lucide-react';

// ─── Status Badge Component ───────────────────────────────────────────────────

export const PRStatusBadge: React.FC<{ state: string; isDraft?: boolean; isMerged?: boolean }> = ({
  state,
  isDraft,
  isMerged,
}) => {
  const s = (state || 'open').toLowerCase();

  if (isMerged || s === 'merged') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
        <CheckCircle2 className="w-3.5 h-3.5 text-purple-500" />
        Merged
      </span>
    );
  }

  if (isDraft || s === 'draft') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
        <Clock className="w-3.5 h-3.5 text-slate-400" />
        Draft
      </span>
    );
  }

  if (s === 'closed') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20">
        <X className="w-3.5 h-3.5 text-red-500" />
        Closed
      </span>
    );
  }

  if (s === 'changes_requested') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
        Changes Requested
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
      <GitPullRequest className="w-3.5 h-3.5 text-emerald-500" />
      Open
    </span>
  );
};

// ─── Main PullRequestsPage ───────────────────────────────────────────────────

export const PullRequestsPage: React.FC<{ repositories?: Repository[] }> = ({ repositories = [] }) => {
  const [repos, setRepos] = useState<Repository[]>(repositories);
  const [selectedRepoId, setSelectedRepoId] = useState<number | 'all'>('all');
  const [prs, setPrs] = useState<PullRequestItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [stateFilter, setStateFilter] = useState<'all' | 'open' | 'draft' | 'merged' | 'closed'>('all');

  // Detail Modal State
  const [detailPR, setDetailPR] = useState<PullRequestItem | null>(null);
  const [refreshingPRNumber, setRefreshingPRNumber] = useState<number | null>(null);

  // Create PR Wizard Modal State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3 | 4>(1);
  const [wizardRepoId, setWizardRepoId] = useState<number>(0);
  const [branchesData, setBranchesData] = useState<RepositoryBranches | null>(null);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [sourceBranch, setSourceBranch] = useState('');
  const [targetBranch, setTargetBranch] = useState('main');

  // Preparation / Comparison Data
  const [preparing, setPreparing] = useState(false);
  const [prepData, setPrepData] = useState<PullRequestPrepareResponse | null>(null);
  const [prepError, setPrepError] = useState<string | null>(null);

  // Editable Form Data
  const [prTitle, setPrTitle] = useState('');
  const [prDescription, setPrDescription] = useState('');
  const [isDraft, setIsDraft] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccessPR, setCreateSuccessPR] = useState<PullRequestItem | null>(null);

  // Load repositories if not provided
  useEffect(() => {
    if (repositories.length > 0) {
      setRepos(repositories);
      if (selectedRepoId === 'all') {
        const first = repositories[0].id || Number(repositories[0].repo_id);
        if (first) {
          setSelectedRepoId(first);
          setWizardRepoId(first);
        }
      }
    } else {
      api.getRepositories().then((r) => {
        setRepos(r);
        if (r.length > 0 && selectedRepoId === 'all') {
          const first = r[0].id || Number(r[0].repo_id);
          if (first) {
            setSelectedRepoId(first);
            setWizardRepoId(first);
          }
        }
      }).catch(() => {});
    }
  }, [repositories]);

  // Load PRs
  const loadPRs = useCallback(async () => {
    if (selectedRepoId === 'all' || !selectedRepoId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.getPullRequests(selectedRepoId);
      setPrs(data);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load Pull Requests');
      setPrs([]);
    } finally {
      setLoading(false);
    }
  }, [selectedRepoId]);

  useEffect(() => {
    loadPRs();
  }, [loadPRs]);

  // Sync PRs with GitHub
  const handleSyncPRs = async () => {
    if (selectedRepoId === 'all' || !selectedRepoId) return;
    setSyncing(true);
    setErrorMsg(null);
    try {
      await api.syncRepositoryPRs(selectedRepoId);
      await loadPRs();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to sync Pull Requests from GitHub');
    } finally {
      setSyncing(false);
    }
  };

  // Refresh single PR
  const handleRefreshPR = async (prNumber: number) => {
    if (!selectedRepoId || selectedRepoId === 'all') return;
    setRefreshingPRNumber(prNumber);
    try {
      const updated = await api.refreshPullRequest(selectedRepoId, prNumber);
      setPrs((prev) => prev.map((p) => (p.pr_number === prNumber ? updated : p)));
      if (detailPR?.pr_number === prNumber) {
        setDetailPR(updated);
      }
    } catch (err: any) {
      setErrorMsg(err.message || `Failed to refresh PR #${prNumber}`);
    } finally {
      setRefreshingPRNumber(null);
    }
  };

  // Wizard: Load branches for selected repo
  const loadBranchesForWizard = async (repoId: number) => {
    setLoadingBranches(true);
    setBranchesData(null);
    try {
      const b = await api.getRepositoryBranches(repoId);
      setBranchesData(b);
      setTargetBranch(b.default_branch || 'main');
      // Set source branch to first local dev branch or first branch
      const devBranch = b.local_branches.find((br: any) => br.name.startsWith('autogit/dev-'));
      if (devBranch) {
        setSourceBranch(devBranch.name);
      } else if (b.local_branches.length > 0) {
        setSourceBranch(b.local_branches[0].name);
      }
    } catch (err: any) {
      setPrepError(err.message || 'Failed to fetch repository branches');
    } finally {
      setLoadingBranches(false);
    }
  };

  // Open Create Wizard
  const openCreateWizard = () => {
    const currentRepoId = (selectedRepoId !== 'all' ? selectedRepoId : repos[0]?.id) || 1;
    setWizardRepoId(Number(currentRepoId));
    setWizardStep(1);
    setPrepData(null);
    setPrepError(null);
    setCreateError(null);
    setCreateSuccessPR(null);
    setIsCreateModalOpen(true);
    loadBranchesForWizard(Number(currentRepoId));
  };

  // Wizard: Step 1 -> Step 2 (Prepare & Compare)
  const handleProceedToCompare = async () => {
    if (!sourceBranch || !targetBranch) {
      setPrepError('Please select both a source branch and a target branch.');
      return;
    }
    if (sourceBranch === targetBranch) {
      setPrepError('Source and target branch cannot be the same.');
      return;
    }

    setPreparing(true);
    setPrepError(null);
    try {
      const prep = await api.preparePullRequest(wizardRepoId, {
        source_branch: sourceBranch,
        target_branch: targetBranch,
      });
      setPrepData(prep);
      setPrTitle(prep.suggested_title || `feat: merge ${sourceBranch} into ${targetBranch}`);
      setPrDescription(prep.suggested_body || '');
      setWizardStep(2);
    } catch (err: any) {
      setPrepError(err.message || 'Failed to prepare branch comparison and pre-PR validation.');
    } finally {
      setPreparing(false);
    }
  };

  // Wizard: Submit PR Creation
  const handleConfirmCreatePR = async () => {
    if (!prTitle.trim()) {
      setCreateError('Pull Request title is required.');
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createPullRequest(wizardRepoId, {
        source_branch: sourceBranch,
        target_branch: targetBranch,
        title: prTitle.trim(),
        description: prDescription.trim() || undefined,
        is_draft: isDraft,
      });
      setCreateSuccessPR(created);
      setWizardStep(4);
      // Refresh list
      loadPRs();
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create Pull Request on GitHub.');
    } finally {
      setCreating(false);
    }
  };

  // Filtered PR list
  const filteredPRs = prs.filter((p) => {
    if (stateFilter !== 'all') {
      const s = (p.state || 'open').toLowerCase();
      if (stateFilter === 'merged' && !p.is_merged && s !== 'merged') return false;
      if (stateFilter === 'draft' && !p.is_draft && s !== 'draft') return false;
      if (stateFilter === 'open' && (p.is_merged || p.is_draft || s === 'closed')) return false;
      if (stateFilter === 'closed' && (p.is_merged || s !== 'closed')) return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = (p.title || '').toLowerCase().includes(q);
      const matchNum = `#${p.pr_number}`.includes(q);
      const matchBranch = (p.source_branch || '').toLowerCase().includes(q) || (p.target_branch || '').toLowerCase().includes(q);
      return matchTitle || matchNum || matchBranch;
    }
    return true;
  });

  // Summary counts
  const totalCount = prs.length;
  const openCount = prs.filter((p) => !p.is_merged && !p.is_draft && p.state.toLowerCase() === 'open').length;
  const draftCount = prs.filter((p) => p.is_draft || p.state.toLowerCase() === 'draft').length;
  const mergedCount = prs.filter((p) => p.is_merged || p.state.toLowerCase() === 'merged').length;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <GitPullRequest className="w-7 h-7 text-indigo-500" />
            Pull Request Automation
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Prepare, validate, and create GitHub Pull Requests with multi-stage autonomous safety gates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncPRs}
            disabled={syncing || selectedRepoId === 'all'}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 rounded-xl transition-all shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin text-indigo-500' : ''}`} />
            <span>{syncing ? 'Syncing...' : 'Sync with GitHub'}</span>
          </button>
          <button
            onClick={openCreateWizard}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-all shadow-md shadow-indigo-600/30"
          >
            <Plus className="w-4 h-4" />
            <span>New Pull Request</span>
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Total PRs Tracked</span>
            <GitPullRequest className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white mt-2">{totalCount}</div>
        </div>
        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between text-emerald-500 text-xs font-medium">
            <span>Open Pull Requests</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">{openCount}</div>
        </div>
        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Draft PRs</span>
            <Clock className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-700 dark:text-slate-300 mt-2">{draftCount}</div>
        </div>
        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between text-purple-500 text-xs font-medium">
            <span>Merged PRs</span>
            <CheckCircle2 className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 mt-2">{mergedCount}</div>
        </div>
      </div>

      {/* Filter and Control Bar */}
      <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Repo selector */}
          <div className="flex items-center gap-2">
            <FolderGit2 className="w-4 h-4 text-slate-400 shrink-0" />
            <select
              value={selectedRepoId}
              onChange={(e) => setSelectedRepoId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              className="px-3 py-1.5 text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {repos.map((r) => (
                <option key={r.id || r.repo_id} value={r.id || r.repo_id}>
                  {r.repository_name || r.name} (ID: {r.id || r.repo_id})
                </option>
              ))}
            </select>
          </div>

          {/* Search box */}
          <div className="relative flex-1 max-w-sm">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by title, branch, or #number..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* State tabs */}
        <div className="flex items-center gap-1.5 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
          {(['all', 'open', 'draft', 'merged', 'closed'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setStateFilter(st)}
              className={`px-3 py-1 rounded-lg font-medium transition-all capitalize ${
                stateFilter === st
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Error alert banner */}
      {errorMsg && (
        <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-xs text-red-700 dark:text-red-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-600">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* PR Table List */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            <span className="text-xs">Loading Pull Requests from database...</span>
          </div>
        ) : filteredPRs.length === 0 ? (
          <div className="py-16 text-center space-y-3">
            <GitPullRequest className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto" />
            <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No Pull Requests found
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
              No Pull Requests match the selected filters. Use "New Pull Request" to prepare and create a PR from an autonomous development branch.
            </p>
            <button
              onClick={openCreateWizard}
              className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-all shadow-md shadow-indigo-600/30"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Pull Request</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 text-slate-500 uppercase tracking-wider font-semibold">
                <tr>
                  <th className="py-3 px-4">PR # & Title</th>
                  <th className="py-3 px-4">Branches</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Created / Synced</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-sans">
                {filteredPRs.map((pr) => (
                  <tr
                    key={pr.id || pr.pr_number}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex items-start gap-2">
                        <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                          #{pr.pr_number}
                        </span>
                        <div>
                          <div className="font-semibold text-slate-900 dark:text-white line-clamp-1">
                            {pr.title}
                          </div>
                          {pr.html_url && (
                            <a
                              href={pr.html_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[11px] text-slate-400 hover:text-indigo-500 inline-flex items-center gap-1 mt-0.5"
                            >
                              <span>Open on GitHub</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 font-mono text-[11px]">
                        <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium truncate max-w-[140px]">
                          {pr.source_branch}
                        </span>
                        <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
                        <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium truncate max-w-[140px]">
                          {pr.target_branch}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <PRStatusBadge state={pr.state} isDraft={pr.is_draft} isMerged={pr.is_merged} />
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 text-[11px]">
                      <div>{pr.created_at ? new Date(pr.created_at).toLocaleDateString() : 'N/A'}</div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        Synced: {pr.last_synced_at ? new Date(pr.last_synced_at).toLocaleTimeString() : 'N/A'}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => setDetailPR(pr)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                          title="View details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleRefreshPR(pr.pr_number)}
                          disabled={refreshingPRNumber === pr.pr_number}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
                          title="Refresh status from GitHub"
                        >
                          <RefreshCw className={`w-4 h-4 ${refreshingPRNumber === pr.pr_number ? 'animate-spin text-indigo-500' : ''}`} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── Detail Modal ──────────────────────────────────────────────────────── */}
      {detailPR && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full border border-slate-200 dark:border-slate-700 flex flex-col max-h-[85vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2.5">
                <GitPullRequest className="w-5 h-5 text-indigo-500" />
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <span>PR #{detailPR.pr_number}: {detailPR.title}</span>
                  </h3>
                </div>
              </div>
              <button
                onClick={() => setDetailPR(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4 text-xs">
              <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700">
                <div className="space-y-1">
                  <div className="text-slate-500 font-medium">Lifecycle Status</div>
                  <PRStatusBadge state={detailPR.state} isDraft={detailPR.is_draft} isMerged={detailPR.is_merged} />
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleRefreshPR(detailPR.pr_number)}
                    disabled={refreshingPRNumber === detailPR.pr_number}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-50 font-medium"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshingPRNumber === detailPR.pr_number ? 'animate-spin text-indigo-500' : ''}`} />
                    <span>Refresh</span>
                  </button>
                  {detailPR.html_url && (
                    <a
                      href={detailPR.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 font-medium"
                    >
                      <span>Open on GitHub</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              </div>

              {/* Branch & commit metadata */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 font-mono text-[11px]">
                <div>
                  <span className="text-slate-500 block font-sans text-xs">Source Branch:</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">{detailPR.source_branch}</span>
                  {detailPR.head_commit_sha && (
                    <div className="text-slate-400 text-[10px] mt-0.5 truncate">SHA: {detailPR.head_commit_sha}</div>
                  )}
                </div>
                <div>
                  <span className="text-slate-500 block font-sans text-xs">Target Branch:</span>
                  <span className="text-indigo-600 dark:text-indigo-400 font-bold">{detailPR.target_branch}</span>
                  {detailPR.base_commit_sha && (
                    <div className="text-slate-400 text-[10px] mt-0.5 truncate">Base: {detailPR.base_commit_sha}</div>
                  )}
                </div>
              </div>

              {/* Description Body */}
              <div>
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Description / Body
                </label>
                <div className="p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 font-mono whitespace-pre-wrap text-slate-800 dark:text-slate-200 max-h-56 overflow-y-auto">
                  {detailPR.body || 'No description provided.'}
                </div>
              </div>

              {/* Note on AutoGit PR Scope */}
              <div className="p-2.5 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-lg text-blue-800 dark:text-blue-300 text-[11px]">
                <strong>Note:</strong> AutoGit AI prepares, validates, and creates Pull Requests, but will never automatically merge them. Merging is performed directly by the repository maintainer on GitHub.
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex justify-end">
              <button
                onClick={() => setDetailPR(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 rounded-lg text-slate-700 dark:text-slate-200 font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Create PR Wizard Modal ────────────────────────────────────────────── */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full border border-slate-200 dark:border-slate-700 flex flex-col max-h-[90vh] overflow-hidden">
            {/* Wizard Header */}
            <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <GitPullRequest className="w-5 h-5 text-indigo-500" />
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  Create GitHub Pull Request
                </h3>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Step Progress Pills */}
            <div className="px-5 pt-3 pb-2 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
              <div className={`font-semibold flex items-center gap-1.5 ${wizardStep === 1 ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`}>
                <span className="w-5 h-5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 flex items-center justify-center text-[10px]">1</span>
                <span>Select Branches</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <div className={`font-semibold flex items-center gap-1.5 ${wizardStep === 2 ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`}>
                <span className="w-5 h-5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 flex items-center justify-center text-[10px]">2</span>
                <span>Compare & Validate</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <div className={`font-semibold flex items-center gap-1.5 ${wizardStep === 3 ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`}>
                <span className="w-5 h-5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 flex items-center justify-center text-[10px]">3</span>
                <span>Title & Review</span>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <div className={`font-semibold flex items-center gap-1.5 ${wizardStep === 4 ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`}>
                <span className="w-5 h-5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 flex items-center justify-center text-[10px]">4</span>
                <span>Complete</span>
              </div>
            </div>

            {/* Wizard Content */}
            <div className="p-5 overflow-y-auto space-y-4 text-xs flex-1">
              {/* Step 1: Select Branches */}
              {wizardStep === 1 && (
                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                      Target Repository
                    </label>
                    <select
                      value={wizardRepoId}
                      onChange={(e) => {
                        const rid = Number(e.target.value);
                        setWizardRepoId(rid);
                        loadBranchesForWizard(rid);
                      }}
                      className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl"
                    >
                      {repos.map((r) => (
                        <option key={r.id || r.repo_id} value={r.id || r.repo_id}>
                          {r.repository_name || r.name} (ID: {r.id || r.repo_id})
                        </option>
                      ))}
                    </select>
                  </div>

                  {loadingBranches ? (
                    <div className="py-8 flex flex-col items-center justify-center gap-2 text-slate-500">
                      <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                      <span>Discovering local and remote branches...</span>
                    </div>
                  ) : branchesData ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* Source Branch */}
                      <div>
                        <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                          Source Branch (Your Changes)
                        </label>
                        <select
                          value={sourceBranch}
                          onChange={(e) => setSourceBranch(e.target.value)}
                          className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl font-mono"
                        >
                          {branchesData.local_branches.map((b) => (
                            <option key={b.name} value={b.name}>
                              {b.name} {b.name.startsWith('autogit/dev-') ? '(autonomous)' : ''}
                            </option>
                          ))}
                        </select>
                        <span className="text-[10px] text-slate-400 mt-1 block">
                          Development branch containing unmerged changes.
                        </span>
                      </div>

                      {/* Target Branch */}
                      <div>
                        <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                          Target Branch (Destination)
                        </label>
                        <select
                          value={targetBranch}
                          onChange={(e) => setTargetBranch(e.target.value)}
                          className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl font-mono"
                        >
                          {branchesData.remote_branches.length > 0
                            ? branchesData.remote_branches.map((b) => (
                                <option key={b.name} value={b.name}>
                                  {b.name} (remote)
                                </option>
                              ))
                            : branchesData.local_branches.map((b) => (
                                <option key={b.name} value={b.name}>
                                  {b.name}
                                </option>
                              ))}
                        </select>
                        <span className="text-[10px] text-slate-400 mt-1 block">
                          Base branch to merge changes into.
                        </span>
                      </div>
                    </div>
                  ) : null}

                  {prepError && (
                    <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-300 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{prepError}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Compare & Validate */}
              {wizardStep === 2 && prepData && (
                <div className="space-y-4">
                  {/* Commits & Stats Summary */}
                  <div className="grid grid-cols-3 gap-3 p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 text-center">
                    <div>
                      <div className="text-slate-500 text-[11px]">Commits Ahead</div>
                      <div className="text-base font-bold text-indigo-600 dark:text-indigo-400 mt-0.5">
                        +{prepData.ahead_count}
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500 text-[11px]">Files Changed</div>
                      <div className="text-base font-bold text-slate-800 dark:text-slate-200 mt-0.5">
                        {prepData.changed_files_count}
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500 text-[11px]">Changes</div>
                      <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                        +{prepData.additions} / -{prepData.deletions}
                      </div>
                    </div>
                  </div>

                  {/* Pre-PR Validation Checklist */}
                  <div>
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-2">
                      Pre-PR Autonomous Safety Verification
                    </label>
                    <div className="space-y-1.5">
                      {prepData.validation.checks.map((chk, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between p-2.5 bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded-xl"
                        >
                          <div className="flex items-center gap-2">
                            {chk.status === 'PASSED' ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                            ) : chk.status === 'WARNING' ? (
                              <AlertTriangle className="w-4 h-4 text-amber-500" />
                            ) : (
                              <X className="w-4 h-4 text-red-500" />
                            )}
                            <span className="font-semibold text-slate-800 dark:text-slate-200">{chk.name}</span>
                          </div>
                          <span className="text-[11px] text-slate-500">{chk.message || chk.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Blocking Reasons Alert */}
                  {!prepData.can_create && prepData.blocking_reasons.length > 0 && (
                    <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-300 space-y-1">
                      <div className="font-bold flex items-center gap-1.5">
                        <AlertCircle className="w-4 h-4" />
                        <span>Pull Request Creation Blocked:</span>
                      </div>
                      <ul className="list-disc pl-5 space-y-0.5 text-[11px]">
                        {prepData.blocking_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Commits Included List */}
                  <div>
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                      Commits ({prepData.commits.length})
                    </label>
                    <div className="max-h-28 overflow-y-auto space-y-1 bg-slate-50 dark:bg-slate-900/40 p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 font-mono text-[11px]">
                      {prepData.commits.map((c) => (
                        <div key={c.sha} className="flex items-center gap-2">
                          <span className="font-bold text-indigo-600 dark:text-indigo-400">{c.short_sha}</span>
                          <span className="text-slate-700 dark:text-slate-300 truncate">{c.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Step 3: Title & Review */}
              {wizardStep === 3 && (
                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                      Pull Request Title *
                    </label>
                    <input
                      type="text"
                      value={prTitle}
                      onChange={(e) => setPrTitle(e.target.value)}
                      className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl font-medium"
                      placeholder="e.g. feat: add automated github push validation"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                      Description / Body
                    </label>
                    <textarea
                      rows={8}
                      value={prDescription}
                      onChange={(e) => setPrDescription(e.target.value)}
                      className="w-full p-3 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl font-mono"
                      placeholder="Markdown description of changes..."
                    />
                  </div>

                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={isDraft}
                      onChange={(e) => setIsDraft(e.target.checked)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="font-medium text-slate-700 dark:text-slate-300">
                      Create as Draft Pull Request (not ready for final review)
                    </span>
                  </label>

                  {createError && (
                    <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-300 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{createError}</span>
                    </div>
                  )}

                  <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl text-amber-800 dark:text-amber-200 text-[11px]">
                    <strong>Explicit Approval Required:</strong> Creating this Pull Request will publish your branch and changes to the remote GitHub repository. AutoGit AI will never automatically merge this PR.
                  </div>
                </div>
              )}

              {/* Step 4: Success Completion */}
              {wizardStep === 4 && createSuccessPR && (
                <div className="py-8 text-center space-y-4">
                  <div className="w-12 h-12 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto">
                    <Check className="w-6 h-6" />
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-slate-900 dark:text-white">
                      Pull Request Successfully Created!
                    </h4>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      GitHub PR #{createSuccessPR.pr_number} has been created and registered in AutoGit AI.
                    </p>
                  </div>

                  <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 text-left font-mono text-xs max-w-md mx-auto space-y-1">
                    <div><strong>Title:</strong> {createSuccessPR.title}</div>
                    <div><strong>Branches:</strong> {createSuccessPR.source_branch} &rarr; {createSuccessPR.target_branch}</div>
                    <div><strong>State:</strong> {createSuccessPR.state.toUpperCase()}</div>
                  </div>

                  {createSuccessPR.html_url && (
                    <div>
                      <a
                        href={createSuccessPR.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-500 shadow-md shadow-indigo-600/30"
                      >
                        <span>View Pull Request on GitHub</span>
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Wizard Footer Controls */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-700 flex justify-between items-center">
              {wizardStep > 1 && wizardStep < 4 ? (
                <button
                  onClick={() => setWizardStep((prev) => (prev - 1) as any)}
                  className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 rounded-lg text-slate-700 dark:text-slate-200 font-medium"
                >
                  Back
                </button>
              ) : <div />}

              <div className="flex items-center gap-2">
                {wizardStep === 1 && (
                  <button
                    onClick={handleProceedToCompare}
                    disabled={preparing || loadingBranches || !sourceBranch || !targetBranch}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold disabled:opacity-50"
                  >
                    {preparing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Comparing Branches...</span>
                      </>
                    ) : (
                      <>
                        <span>Compare & Validate</span>
                        <ChevronRight className="w-4 h-4" />
                      </>
                    )}
                  </button>
                )}

                {wizardStep === 2 && (
                  <button
                    onClick={() => setWizardStep(3)}
                    disabled={!prepData?.can_create}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span>Proceed to Title & Review</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                )}

                {wizardStep === 3 && (
                  <button
                    onClick={handleConfirmCreatePR}
                    disabled={creating || !prTitle.trim()}
                    className="inline-flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-semibold disabled:opacity-50 shadow-md shadow-emerald-600/20"
                  >
                    {creating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Creating on GitHub...</span>
                      </>
                    ) : (
                      <>
                        <GitPullRequest className="w-4 h-4" />
                        <span>Confirm & Create Pull Request</span>
                      </>
                    )}
                  </button>
                )}

                {wizardStep === 4 && (
                  <button
                    onClick={() => setIsCreateModalOpen(false)}
                    className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 rounded-xl text-slate-700 dark:text-slate-200 font-semibold"
                  >
                    Done
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
