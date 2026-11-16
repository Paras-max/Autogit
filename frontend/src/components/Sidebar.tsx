import React from 'react';
import {
  LayoutDashboard,
  FolderGit2,
  CalendarDays,
  Bot,
  GitCommit,
  Github,
  ShieldCheck,
  Activity,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
  GitPullRequest,
} from 'lucide-react';

export type NavTab =
  | 'overview'
  | 'repositories'
  | 'scheduler'
  | 'agents'
  | 'commits'
  | 'github'
  | 'pull_requests'
  | 'validation'
  | 'activity'
  | 'notifications'
  | 'settings';

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  unreadCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  collapsed,
  onToggleCollapse,
  unreadCount,
}) => {
  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'repositories', label: 'Repositories', icon: FolderGit2 },
    { id: 'scheduler', label: 'Development Scheduler', icon: CalendarDays },
    { id: 'agents', label: 'AI Agents', icon: Bot },
    { id: 'commits', label: 'Commit History', icon: GitCommit },
    { id: 'github', label: 'GitHub Sync', icon: Github },
    { id: 'pull_requests', label: 'Pull Requests', icon: GitPullRequest },
    { id: 'validation', label: 'Validation & Security', icon: ShieldCheck },
    { id: 'activity', label: 'Activity Logs', icon: Activity },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: unreadCount },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={`relative flex flex-col bg-slate-900 border-r border-slate-800 transition-all duration-300 z-20 ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* App Branding */}
      <div className="flex items-center justify-between p-4 h-16 border-b border-slate-800">
        <div className="flex items-center space-x-3 overflow-hidden">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shrink-0 shadow-lg shadow-blue-500/20">
            <GitPullRequest className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <div className="truncate">
              <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-blue-400 bg-clip-text text-transparent">
                AutoGit AI
              </span>
              <span className="block text-[10px] text-blue-400 font-mono uppercase tracking-wider font-semibold">
                Autonomous IDE-Free
              </span>
            </div>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id as NavTab)}
              className={`w-full flex items-center px-3 py-2.5 rounded-xl text-sm font-medium transition-all group ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
              }`}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                className={`w-5 h-5 shrink-0 transition-transform ${
                  isActive ? 'text-white' : 'text-slate-400 group-hover:text-white'
                }`}
              />
              {!collapsed && (
                <span className="ml-3 truncate flex-1 text-left">{item.label}</span>
              )}
              {item.badge && item.badge > 0 ? (
                <span
                  className={`inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold leading-none rounded-full ${
                    isActive ? 'bg-white text-blue-600' : 'bg-blue-500 text-white'
                  }`}
                >
                  {item.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800 text-xs text-slate-500 flex items-center justify-between">
        {!collapsed && <span>v0.4.0 Phase 4</span>}
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50" title="Engine Operational"></span>
      </div>
    </aside>
  );
};

