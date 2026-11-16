import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar, NavTab } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { OverviewPage } from './pages/OverviewPage';
import { RepositoriesPage } from './pages/RepositoriesPage';
import { SchedulerPage } from './pages/SchedulerPage';
import { AIAgentsPage } from './pages/AIAgentsPage';
import { CommitHistoryPage } from './pages/CommitHistoryPage';
import { GitHubSyncPage } from './pages/GitHubSyncPage';
import { PullRequestsPage } from './pages/PullRequestsPage';
import { ValidationPage } from './pages/ValidationPage';
import { ActivityPage } from './pages/ActivityPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { SettingsPage } from './pages/SettingsPage';
import { useSSE } from './hooks/useSSE';
import { api } from './services/api';
import {
  Repository,
  DashboardOverview,
  DashboardActivity,
  CommitRecord,
  WeeklySchedule,
} from './types';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // ── Shared data ───────────────────────────────────────────────────────────
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [activity, setActivity] = useState<DashboardActivity[]>([]);
  const [commits, setCommits] = useState<CommitRecord[]>([]);
  const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // ── Dark mode ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem('autogit_theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.classList.toggle('dark', stored === 'dark' || (!stored && prefersDark));
  }, []);

  // ── SSE ───────────────────────────────────────────────────────────────────
  const { connected: sseConnected, lastEvent } = useSSE();

  // ── Data loaders ──────────────────────────────────────────────────────────
  const loadNotifications = useCallback(async () => {
    try {
      const data = await api.getNotifications(10, false);
      const list = Array.isArray(data) ? data : [];
      setNotifications(list);
      setUnreadCount(list.filter((n: any) => !n.is_read && !n.read).length);
    } catch { /* ignore */ }
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [repos, ov, act, coms, sched] = await Promise.allSettled([
        api.getRepositories(),
        api.getDashboardOverview(),
        api.getDashboardActivity(50),
        api.getCommitHistory(undefined, 50),
        api.getWeeklySchedule(),
      ]);
      if (repos.status === 'fulfilled') setRepositories(repos.value as Repository[]);
      if (ov.status === 'fulfilled') setOverview(ov.value as DashboardOverview);
      if (act.status === 'fulfilled') setActivity(act.value as DashboardActivity[]);
      if (coms.status === 'fulfilled') setCommits(coms.value as CommitRecord[]);
      if (sched.status === 'fulfilled') setSchedule(sched.value as WeeklySchedule);
    } catch { /* ignore */ }
    await loadNotifications();
  }, [loadNotifications]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Reload on SSE events
  useEffect(() => {
    if (lastEvent) {
      loadNotifications();
    }
  }, [lastEvent, loadNotifications]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await loadAll();
    setTimeout(() => setIsRefreshing(false), 800);
  }, [loadAll]);

  const handleMarkAllRead = useCallback(async () => {
    try {
      await api.markAllNotificationsRead();
      await loadNotifications();
    } catch { /* ignore */ }
  }, [loadNotifications]);

  // ── Page renderer ─────────────────────────────────────────────────────────
  const renderPage = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <OverviewPage
            overview={overview}
            activity={activity}
            commits={commits as any}
            repositories={repositories}
            onNavigate={setActiveTab}
            onRefresh={handleRefresh}
          />
        );
      case 'repositories':
        return (
          <RepositoriesPage
            repositories={repositories}
            onRefresh={handleRefresh}
          />
        );
      case 'scheduler':
        return (
          <SchedulerPage
            schedule={schedule}
            onRefresh={handleRefresh}
          />
        );
      case 'agents':
        return <AIAgentsPage repositories={repositories} />;
      case 'commits':
        return <CommitHistoryPage />;
      case 'github':
        return <GitHubSyncPage />;
      case 'pull_requests':
        return <PullRequestsPage repositories={repositories} />;
      case 'validation':
        return <ValidationPage />;
      case 'activity':
        return <ActivityPage />;
      case 'notifications':
        return <NotificationsPage />;
      case 'settings':
        return <SettingsPage />;
      default:
        return (
          <OverviewPage
            overview={overview}
            activity={activity}
            commits={commits as any}
            repositories={repositories}
            onNavigate={setActiveTab}
            onRefresh={handleRefresh}
          />
        );
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900 overflow-hidden font-sans">
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        unreadCount={unreadCount}
      />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Navbar
          sseConnected={sseConnected}
          unreadCount={unreadCount}
          notifications={notifications}
          onMarkAllRead={handleMarkAllRead}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
          onOpenNotificationsTab={() => setActiveTab('notifications')}
        />
        <main className="flex-1 overflow-y-auto p-6">{renderPage()}</main>
      </div>
    </div>
  );
};

export default App;
