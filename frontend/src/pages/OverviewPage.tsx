import React from 'react';
import {
  FolderGit2,
  CheckCircle,
  PlayCircle,
  GitCommit,
  Clock,
  AlertTriangle,
  Bot,
  Activity,
  Calendar,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import {
  DashboardActivity,
  DashboardOverview,
  Repository,
  CommitItem,
} from '../types';

interface OverviewPageProps {
  overview: DashboardOverview | null;
  activity: DashboardActivity[];
  commits: CommitItem[];
  repositories: Repository[];
  onNavigate: (tab: any) => void;
  onRefresh: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  overview,
  activity,
  commits,
  repositories,
  onNavigate,
}) => {
  const stats = [
    {
      title: 'Total Repositories',
      value: overview?.total_repositories ?? 0,
      icon: FolderGit2,
      color: 'from-blue-600 to-cyan-500',
      action: () => onNavigate('repositories'),
    },
    {
      title: 'Authorized Repos',
      value: overview?.authorized_repositories ?? 0,
      icon: CheckCircle,
      color: 'from-emerald-600 to-teal-500',
      action: () => onNavigate('repositories'),
    },
    {
      title: 'Active Dev Sessions',
      value: overview?.active_sessions ?? 0,
      icon: PlayCircle,
      color: 'from-violet-600 to-purple-500',
      action: () => onNavigate('agents'),
    },
    {
      title: 'Commits Created',
      value: overview?.total_commits ?? 0,
      icon: GitCommit,
      color: 'from-indigo-600 to-blue-500',
      action: () => onNavigate('commits'),
    },
    {
      title: 'Pending Approvals',
      value: overview?.pending_approvals ?? 0,
      icon: Clock,
      color: overview?.pending_approvals ? 'from-amber-600 to-yellow-500' : 'from-slate-700 to-slate-600',
      action: () => onNavigate('activity'),
    },
    {
      title: 'Validation Failures',
      value: overview?.validation_failures ?? 0,
      icon: AlertTriangle,
      color: overview?.validation_failures ? 'from-rose-600 to-red-500' : 'from-slate-700 to-slate-600',
      action: () => onNavigate('validation'),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="rounded-3xl bg-gradient-to-r from-blue-900/40 via-indigo-900/30 to-slate-900 border border-blue-500/20 p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 -mr-8 -mt-8 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              AutoGit AI Dashboard
            </h1>
            <p className="text-slate-300 text-sm mt-1">
              Autonomous IDE-independent Git operations, 5-day random scheduler, and controlled GitHub sync.
            </p>
          </div>
          <div className="flex items-center space-x-3 shrink-0">
            <span className="px-3.5 py-1.5 rounded-full bg-slate-800/80 border border-slate-700 text-xs font-mono text-blue-300">
              ISO Week: {overview?.current_week || 'Current'}
            </span>
            <button
              onClick={() => onNavigate('repositories')}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all flex items-center space-x-2"
            >
              <span>Manage Repos</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {stats.map((s, idx) => {
          const Icon = s.icon;
          return (
            <div
              key={idx}
              onClick={s.action}
              className="bg-slate-900/90 border border-slate-800/80 rounded-2xl p-4 hover:border-slate-700 transition-all cursor-pointer group hover:shadow-lg"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 truncate">{s.title}</span>
                <div className={`w-7 h-7 rounded-lg bg-gradient-to-br ${s.color} flex items-center justify-center shrink-0`}>
                  <Icon className="w-4 h-4 text-white" />
                </div>
              </div>
              <div className="mt-3 text-2xl font-bold text-white">{s.value}</div>
            </div>
          );
        })}
      </div>

      {/* Main Grid: Activity & Recent Commits */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Activity (2 cols) */}
        <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-blue-400" />
              <h2 className="font-semibold text-sm text-white">Recent Automation Activity</h2>
            </div>
            <button
              onClick={() => onNavigate('activity')}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium"
            >
              View all
            </button>
          </div>
          <div className="divide-y divide-slate-800/60 mt-2">
            {activity.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No recent activity recorded.
              </div>
            ) : (
              activity.slice(0, 6).map((item) => (
                <div key={item.id} className="py-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                        item.status === 'committed' || item.status === 'completed'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                          : item.status === 'awaiting_approval'
                          ? 'bg-amber-950 text-amber-300 border border-amber-800/60'
                          : 'bg-slate-800 text-slate-300'
                      }`}>
                        {item.status}
                      </span>
                      <span className="text-xs font-semibold text-slate-200">{item.title}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-1">{item.description}</p>
                  </div>
                  <span className="text-[10px] text-slate-500 shrink-0 font-mono mt-0.5">
                    {item.timestamp ? item.timestamp.slice(11, 16) : ''}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Recent Commits (1 col) */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
            <div className="flex items-center space-x-2">
              <GitCommit className="w-4 h-4 text-blue-400" />
              <h2 className="font-semibold text-sm text-white">Recent Commits</h2>
            </div>
            <button
              onClick={() => onNavigate('commits')}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium"
            >
              View all
            </button>
          </div>
          <div className="divide-y divide-slate-800/60 mt-2">
            {commits.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No commits recorded yet.
              </div>
            ) : (
              commits.slice(0, 5).map((c, idx) => (
                <div key={idx} className="py-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-blue-400 font-semibold">{c.short_hash}</span>
                    <span className="text-[10px] text-slate-500">{c.repository_name}</span>
                  </div>
                  <p className="text-xs text-slate-300 mt-1 line-clamp-2">{c.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

