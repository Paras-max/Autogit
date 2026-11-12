import React, { useState, useEffect } from 'react';
import {
  FolderGit2,
  Plus,
  Trash2,
  Shield,
  CheckCircle2,
  XCircle,
  GitBranch,
  ExternalLink,
  AlertTriangle,
  Play,
} from 'lucide-react';
import { Repository, RepositoryPermissions } from '../types';
import {
  addRepository,
  removeRepository,
  getRepositoryPermissions,
  updateRepositoryPermissions,
  enableDevelopment,
  disableDevelopment,
  runDevelopmentSession,
} from '../services/api';

interface RepositoriesPageProps {
  repositories: Repository[];
  onRefresh: () => void;
}

export const RepositoriesPage: React.FC<RepositoriesPageProps> = ({
  repositories,
  onRefresh,
}) => {
  const [newPath, setNewPath] = useState('');
  const [newName, setNewName] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Selected repo for permissions detail
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [permissions, setPermissions] = useState<RepositoryPermissions | null>(null);
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({ isOpen: false, title: '', message: '', onConfirm: () => {} });

  const [devRunning, setDevRunning] = useState(false);
  const [devMessage, setDevMessage] = useState<string | null>(null);

  useEffect(() => {
    if (repositories.length > 0 && !selectedRepo) {
      handleSelectRepo(repositories[0]);
    }
  }, [repositories]);

  const handleSelectRepo = async (repo: Repository) => {
    setSelectedRepo(repo);
    setLoadingPerms(true);
    try {
      const p = await getRepositoryPermissions(repo.id);
      setPermissions(p);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoadingPerms(false);
    }
  };

  const handleAddRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPath.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      await addRepository(newPath.trim(), newName.trim() || undefined);
      setNewPath('');
      setNewName('');
      onRefresh();
    } catch (err: any) {
      setAddError(err.message || 'Failed to register repository');
    } finally {
      setAdding(false);
    }
  };

  const handleRemoveRepo = (repo: Repository) => {
    setConfirmModal({
      isOpen: true,
      title: 'Remove Repository Registration?',
      message: `Are you sure you want to remove '${repo.repository_name}' from AutoGit AI? Local files and Git commit history will remain completely untouched.`,
      onConfirm: async () => {
        try {
          await removeRepository(repo.id);
          setSelectedRepo(null);
          setPermissions(null);
          onRefresh();
        } catch (err: any) {
          alert(`Error removing repo: ${err.message}`);
        }
      },
    });
  };

  const handleTogglePermission = async (
    key: keyof RepositoryPermissions,
    currentValue: boolean,
    isDangerous = false
  ) => {
    if (!selectedRepo || !permissions) return;

    const executeToggle = async () => {
      try {
        const updated = await updateRepositoryPermissions(selectedRepo.id, {
          [key]: !currentValue,
        });
        setPermissions(updated);
      } catch (err: any) {
        alert(`Error updating permission: ${err.message}`);
      }
    };

    if (!currentValue && isDangerous) {
      setConfirmModal({
        isOpen: true,
        title: `Enable Dangerous Permission: ${String(key).replace(/_/g, ' ').toUpperCase()}`,
        message: `Enabling ${key} allows AutoGit AI to perform active actions on '${selectedRepo.repository_name}'. Ensure you want to authorize this operation.`,
        onConfirm: executeToggle,
      });
    } else {
      await executeToggle();
    }
  };

  const handleRunDevelopment = async () => {
    if (!selectedRepo) return;
    setDevRunning(true);
    setDevMessage(null);
    try {
      const res = await runDevelopmentSession(selectedRepo.id, true);
      setDevMessage(`Session ${res.status.toUpperCase()}: ${res.tasks_summary || res.branch_name}`);
      onRefresh();
    } catch (err: any) {
      setDevMessage(`Error: ${err.message}`);
    } finally {
      setDevRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Add Repository */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-6 rounded-2xl">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center space-x-2">
            <FolderGit2 className="w-5 h-5 text-blue-400" />
            <span>Repository Management & Permissions</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Register local repositories and configure granular permissions. Unauthorized repositories are strictly barred.
          </p>
        </div>

        {/* Add Repo Form */}
        <form onSubmit={handleAddRepo} className="flex flex-col sm:flex-row items-center gap-2">
          <input
            type="text"
            placeholder="Local repo path (e.g. C:/Projects/repo)"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 w-full sm:w-64"
          />
          <input
            type="text"
            placeholder="Optional name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 w-full sm:w-32"
          />
          <button
            type="submit"
            disabled={adding}
            className="w-full sm:w-auto px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all shadow-md shadow-blue-600/30 shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>{adding ? 'Adding...' : 'Add Repo'}</span>
          </button>
        </form>
      </div>

      {addError && (
        <div className="p-3 bg-red-950/60 border border-red-800 rounded-xl text-xs text-red-300 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{addError}</span>
        </div>
      )}

      {/* Main Repositories Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Repositories List (5 cols) */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm flex flex-col h-[650px]">
          <div className="text-xs font-semibold text-slate-400 px-2 pb-3 border-b border-slate-800 flex items-center justify-between">
            <span>Registered Repositories ({repositories.length})</span>
          </div>

          <div className="flex-1 overflow-y-auto py-2 space-y-2">
            {repositories.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-500">
                No repositories registered yet. Add one above.
              </div>
            ) : (
              repositories.map((repo) => {
                const isSelected = selectedRepo?.id === repo.id;
                return (
                  <div
                    key={repo.id}
                    onClick={() => handleSelectRepo(repo)}
                    className={`p-3 rounded-xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-blue-950/40 border-blue-500/60 shadow-md shadow-blue-950/20'
                        : 'bg-slate-800/40 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm text-white truncate">
                        {repo.repository_name}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        ID: {repo.id}
                      </span>
                    </div>
                    <div className="flex items-center space-x-1.5 text-xs text-slate-400 mt-1.5 font-mono truncate">
                      <GitBranch className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                      <span>{repo.current_branch || 'main'}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-1 truncate" title={repo.repository_path}>
                      {repo.repository_path}
                    </p>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Permissions & Details (7 cols) */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          {selectedRepo && permissions ? (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center space-x-2">
                    <span>{selectedRepo.repository_name}</span>
                  </h2>
                  <p className="text-xs font-mono text-slate-400 mt-1">{selectedRepo.repository_path}</p>
                </div>
                <button
                  onClick={() => handleRemoveRepo(selectedRepo)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 hover:bg-red-950/50 hover:text-red-300 border border-red-900/60 transition-colors flex items-center space-x-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Unregister</span>
                </button>
              </div>

              {/* Permissions Matrix */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center space-x-2">
                  <Shield className="w-4 h-4 text-blue-400" />
                  <span>Independent Repository Permissions</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Permission 1: Monitoring */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">1. File Monitoring</span>
                      <span className="text-[10px] text-slate-400">Detect file events and read diffs</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('monitoring_enabled', permissions.monitoring_enabled)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.monitoring_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.monitoring_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>

                  {/* Permission 2: AI Analysis */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">2. AI Analysis</span>
                      <span className="text-[10px] text-slate-400">Code understanding & commit generator</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('ai_analysis_enabled', permissions.ai_analysis_enabled)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.ai_analysis_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.ai_analysis_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>

                  {/* Permission 3: Autonomous Development */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">3. Autonomous Development</span>
                      <span className="text-[10px] text-amber-400 font-medium">Makes code changes in isolated worktree</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('autonomous_development_enabled', permissions.autonomous_development_enabled, true)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.autonomous_development_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.autonomous_development_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>

                  {/* Permission 4: Smart Commit */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">4. Smart Commit</span>
                      <span className="text-[10px] text-slate-400">Proposes commits; awaits approval</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('smart_commit_enabled', permissions.smart_commit_enabled)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.smart_commit_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.smart_commit_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>

                  {/* Permission 5: Auto Commit */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">5. Auto Commit</span>
                      <span className="text-[10px] text-amber-400 font-medium">Auto-commits when all validations pass</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('auto_commit_enabled', permissions.auto_commit_enabled, true)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.auto_commit_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.auto_commit_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>

                  {/* Permission 6: Remote Push */}
                  <div className="p-3 bg-slate-800/40 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">6. Remote Push</span>
                      <span className="text-[10px] text-red-400 font-medium">Authorizes pushing commits to GitHub</span>
                    </div>
                    <button
                      onClick={() => handleTogglePermission('remote_push_enabled', permissions.remote_push_enabled, true)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                        permissions.remote_push_enabled
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {permissions.remote_push_enabled ? 'ENABLED' : 'DISABLED'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-2xl flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold text-white block">Run Development Session</span>
                  <span className="text-[10px] text-slate-400">
                    Executes an autonomous session in an isolated worktree for this repository.
                  </span>
                </div>
                <button
                  onClick={handleRunDevelopment}
                  disabled={devRunning || !permissions.autonomous_development_enabled}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-1.5 transition-all shadow-md ${
                    permissions.autonomous_development_enabled
                      ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/30'
                      : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  }`}
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>{devRunning ? 'Executing...' : 'Run Session'}</span>
                </button>
              </div>

              {devMessage && (
                <div className="p-3 bg-slate-800 border border-slate-700 rounded-xl text-xs text-blue-300 font-mono">
                  {devMessage}
                </div>
              )}
            </div>
          ) : (
            <div className="py-24 text-center text-xs text-slate-500">
              Select a repository from the left panel to inspect and configure its permissions.
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center space-x-2 text-amber-400 mb-2">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <h3 className="font-bold text-sm text-white">{confirmModal.title}</h3>
            </div>
            <p className="text-xs text-slate-300 mt-2 leading-relaxed">
              {confirmModal.message}
            </p>
            <div className="flex items-center justify-end space-x-3 mt-6">
              <button
                onClick={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  confirmModal.onConfirm();
                  setConfirmModal({ ...confirmModal, isOpen: false });
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

