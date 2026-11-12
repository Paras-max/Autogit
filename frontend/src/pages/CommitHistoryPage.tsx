import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { CommitRecord, Repository } from '../types';
import { GitCommit, Search, Filter, Calendar, User, Eye, X, FileText, CheckCircle2 } from 'lucide-react';

export const CommitHistoryPage: React.FC = () => {
  const [commits, setCommits] = useState<CommitRecord[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCommit, setSelectedCommit] = useState<CommitRecord | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [selectedRepo]);

  const loadData = async () => {
    setLoading(true);
    try {
      const repos = await api.getRepositories();
      setRepositories(repos);

      const repoParam = selectedRepo === 'all' ? undefined : selectedRepo;
      const history = await api.getCommitHistory(repoParam, 100);
      setCommits(history);
    } catch (err) {
      console.error('Failed to load commits', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredCommits = commits.filter(c => {
    const q = searchQuery.toLowerCase();
    const msg = (c.commit_message || '').toLowerCase();
    const hash = (c.commit_hash || '').toLowerCase();
    const branch = (c.branch || '').toLowerCase();
    const repo = (c.repo_name || '').toLowerCase();
    return msg.includes(q) || hash.includes(q) || branch.includes(q) || repo.includes(q);
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Git Commit History</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Inspect autonomous and verified commits created across all authorized repositories.
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
              {repositories.map(r => (
                <option key={r.repo_id} value={r.name}>{r.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

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

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading commit records...</div>
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
                  <th className="px-6 py-3">Files Changed</th>
                  <th className="px-6 py-3">Timestamp</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {filteredCommits.map((c, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/70 dark:hover:bg-slate-700/30 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-start gap-3">
                        <GitCommit className="w-4 h-4 text-primary-500 mt-1 shrink-0" />
                        <div>
                          <p className="font-medium text-slate-900 dark:text-slate-100 font-mono text-sm leading-snug">
                            {c.commit_message?.split('\n')[0]}
                          </p>
                          <span className="inline-block px-1.5 py-0.5 mt-1 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded font-mono text-xs">
                            {c.commit_hash?.slice(0, 7) || 'N/A'}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{c.repo_name}</span>
                      <p className="text-xs text-slate-400 font-mono">refs/heads/{c.branch || 'main'}</p>
                    </td>
                    <td className="px-6 py-4 text-slate-600 dark:text-slate-300">
                      <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-slate-100 dark:bg-slate-700/60 rounded">
                        <FileText className="w-3.5 h-3.5 text-slate-400" />
                        {c.staged_files?.length || 0} file(s)
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(c.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => setSelectedCommit(c)}
                        className="inline-flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium px-2.5 py-1.5 rounded hover:bg-primary-50 dark:hover:bg-primary-950/40"
                      >
                        <Eye className="w-3.5 h-3.5" /> Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
                  {selectedCommit.commit_message}
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
                    {selectedCommit.repo_name}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Branch</span>
                  <span className="font-mono text-xs text-slate-800 dark:text-slate-200">
                    {selectedCommit.branch}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Status</span>
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5" /> {selectedCommit.status}
                  </span>
                </div>
              </div>

              <div>
                <label className="text-xs uppercase font-bold text-slate-400">Committed Files ({selectedCommit.staged_files?.length || 0})</label>
                <div className="mt-2 space-y-1">
                  {selectedCommit.staged_files?.map((file, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded bg-slate-50 dark:bg-slate-900 text-xs font-mono text-slate-700 dark:text-slate-300">
                      <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                      <span className="truncate">{file}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

