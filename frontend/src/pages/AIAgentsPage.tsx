import React, { useState, useEffect } from 'react';
import {
  Bot,
  Play,
  Plus,
  ListTodo,
  CheckCircle2,
  Clock,
  Sparkles,
  ShieldCheck,
  FileCode,
  Layers,
  MessageSquare,
  Search,
} from 'lucide-react';
import { AIAgentInfo, DevelopmentTask, Repository } from '../types';
import { getTasks, addTask, runDevelopmentSession } from '../services/api';

interface AIAgentsPageProps {
  repositories: Repository[];
}

export const AIAgentsPage: React.FC<AIAgentsPageProps> = ({ repositories }) => {
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(
    repositories.length > 0 ? repositories[0].id : null
  );
  const [tasks, setTasks] = useState<DevelopmentTask[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);

  // New task form
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newType, setNewType] = useState('feature');
  const [newPriority, setNewPriority] = useState('medium');
  const [addingTask, setAddingTask] = useState(false);

  // Run session status
  const [runningSession, setRunningSession] = useState(false);
  const [sessionOutput, setSessionOutput] = useState<any | null>(null);

  const agents: AIAgentInfo[] = [
    { name: 'Diff Analysis Agent', role: 'Chunking, binary filtering, additions/deletions parsing', status: 'online' },
    { name: 'Code Understanding Agent', role: 'Language detection, architecture analysis, risk scoring', status: 'online' },
    { name: 'Change Grouping Agent', role: 'Decomposes multi-file modifications into atomic domains', status: 'online' },
    { name: 'Commit Message Generator', role: 'Formats Conventional Commits with semantic fallbacks', status: 'online' },
    { name: 'Validation Agent', role: 'Secret scanner, policy engine, and test runner orchestration', status: 'online' },
    { name: 'Development Agent', role: 'Executes autonomous development inside isolated Git worktrees', status: 'online' },
    { name: 'Task Planning Agent', role: 'Selects 2-3 targeted, safe modifications per session', status: 'online' },
    { name: 'Development Review Agent', role: 'Pre-commit peer review for task satisfaction and safety', status: 'online' },
  ];

  useEffect(() => {
    if (selectedRepoId) {
      loadTasks(selectedRepoId);
    }
  }, [selectedRepoId]);

  const loadTasks = async (repoId: number) => {
    setLoadingTasks(true);
    try {
      const data = await getTasks(repoId);
      setTasks(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingTasks(false);
    }
  };

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRepoId || !newTitle.trim()) return;
    setAddingTask(true);
    try {
      await addTask(selectedRepoId, {
        title: newTitle.trim(),
        description: newDesc.trim() || undefined,
        task_type: newType,
        priority: newPriority,
      });
      setNewTitle('');
      setNewDesc('');
      loadTasks(selectedRepoId);
    } catch (err: any) {
      alert(`Error creating task: ${err.message}`);
    } finally {
      setAddingTask(false);
    }
  };

  const handleRunSession = async () => {
    if (!selectedRepoId) return;
    setRunningSession(true);
    setSessionOutput(null);
    try {
      const res = await runDevelopmentSession(selectedRepoId, true);
      setSessionOutput(res);
      loadTasks(selectedRepoId);
    } catch (err: any) {
      setSessionOutput({ status: 'failed', error_message: err.message });
    } finally {
      setRunningSession(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center space-x-2">
            <Bot className="w-5 h-5 text-blue-400" />
            <span>AI Agents & Development Engine</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Autonomous multi-agent pipeline orchestrating analysis, planning, code modifications, and peer review.
          </p>
        </div>

        {/* Repository selector for tasks */}
        <div className="flex items-center space-x-2 shrink-0">
          <span className="text-xs text-slate-400">Target Repo:</span>
          <select
            value={selectedRepoId || ''}
            onChange={(e) => setSelectedRepoId(Number(e.target.value))}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-blue-500"
          >
            {repositories.map((r) => (
              <option key={r.id} value={r.id}>
                {r.repository_name} (ID: {r.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 8 AI Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {agents.map((ag, idx) => (
          <div key={idx} className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-700 transition-all">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-white">{ag.name}</span>
              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>{ag.status.toUpperCase()}</span>
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">{ag.role}</p>
          </div>
        ))}
      </div>

      {/* Task Backlog & Session Execution */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Task Backlog (7 cols) */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <ListTodo className="w-4 h-4 text-blue-400" />
                <h2 className="font-bold text-sm text-white">Development Task Backlog</h2>
              </div>
              <span className="text-xs text-slate-500 font-mono">{tasks.length} tasks</span>
            </div>

            {/* Add Task Form */}
            <form onSubmit={handleAddTask} className="mt-4 p-3 bg-slate-800/40 border border-slate-800 rounded-xl space-y-2">
              <input
                type="text"
                placeholder="Task title (e.g. Add unit test for validator)"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <div className="flex items-center space-x-2">
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  className="px-2.5 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-white"
                >
                  <option value="feature">Feature</option>
                  <option value="test">Test</option>
                  <option value="refactor">Refactor</option>
                  <option value="documentation">Documentation</option>
                  <option value="bugfix">Bugfix</option>
                </select>
                <select
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value)}
                  className="px-2.5 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-white"
                >
                  <option value="high">High Priority</option>
                  <option value="medium">Medium Priority</option>
                  <option value="low">Low Priority</option>
                </select>
                <button
                  type="submit"
                  disabled={addingTask || !newTitle.trim()}
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-1 ml-auto"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{addingTask ? 'Adding...' : 'Add Task'}</span>
                </button>
              </div>
            </form>

            {/* Tasks List */}
            <div className="divide-y divide-slate-800/60 mt-4 max-h-[360px] overflow-y-auto">
              {tasks.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-500">
                  No backlog tasks. AutoGit AI will automatically suggest high-value improvements during scheduled sessions.
                </div>
              ) : (
                tasks.map((t) => (
                  <div key={t.id} className="py-3 flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          t.priority === 'high' ? 'bg-rose-950 text-rose-300 border border-rose-800' :
                          t.priority === 'medium' ? 'bg-amber-950 text-amber-300 border border-amber-800' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {t.priority}
                        </span>
                        <span className="text-xs font-semibold text-slate-200">{t.title}</span>
                      </div>
                      {t.description && (
                        <p className="text-xs text-slate-400 mt-1">{t.description}</p>
                      )}
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 shrink-0">
                      {t.task_type}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Development Session Execution (5 cols) */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h2 className="font-bold text-sm text-white mb-2 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-indigo-400" />
              <span>Execute Development Session</span>
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Triggers the Autonomous Development Agent on an isolated worktree. The agent analyzes project context, plans ~2-3 modifications, validates syntax, passes peer review, and stages commits.
            </p>

            <div className="mt-6">
              <button
                onClick={handleRunSession}
                disabled={runningSession || !selectedRepoId}
                className="w-full py-3 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white rounded-xl text-xs font-bold shadow-lg shadow-indigo-600/30 flex items-center justify-center space-x-2 transition-all"
              >
                <Play className="w-4 h-4" />
                <span>{runningSession ? 'Autonomous Agent Running...' : 'Trigger Autonomous Session Now'}</span>
              </button>
            </div>

            {/* Session Result */}
            {sessionOutput && (
              <div className="mt-4 p-4 rounded-xl border bg-slate-800/60 border-slate-700 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-200">Session Status</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    sessionOutput.status === 'completed' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'
                  }`}>
                    {sessionOutput.status}
                  </span>
                </div>
                {sessionOutput.branch_name && (
                  <div>
                    <span className="text-slate-400">Branch: </span>
                    <span className="font-mono text-blue-300">{sessionOutput.branch_name}</span>
                  </div>
                )}
                {sessionOutput.commit_hash && (
                  <div>
                    <span className="text-slate-400">Commit: </span>
                    <span className="font-mono text-emerald-400">{sessionOutput.commit_hash.slice(0, 7)}</span>
                  </div>
                )}
                {sessionOutput.tasks_summary && (
                  <div>
                    <span className="text-slate-400">Summary: </span>
                    <span className="text-slate-300">{sessionOutput.tasks_summary}</span>
                  </div>
                )}
                {sessionOutput.error_message && (
                  <div className="text-rose-400 font-mono mt-1">
                    {sessionOutput.error_message}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

