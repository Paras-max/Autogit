import React, { useState } from 'react';
import {
  Bell,
  RefreshCw,
  Sun,
  Moon,
  Radio,
  CheckCircle2,
  Shield,
  ExternalLink,
} from 'lucide-react';
import { NotificationItem } from '../types';

interface NavbarProps {
  sseConnected: boolean;
  unreadCount: number;
  notifications: NotificationItem[];
  onMarkAllRead: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenNotificationsTab: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  sseConnected,
  unreadCount,
  notifications,
  onMarkAllRead,
  onRefresh,
  isRefreshing,
  onOpenNotificationsTab,
}) => {
  const [showNotifMenu, setShowNotifMenu] = useState(false);
  const [isDark, setIsDark] = useState(true);

  const toggleTheme = () => {
    setIsDark(!isDark);
    document.documentElement.classList.toggle('dark');
  };

  return (
    <header className="h-16 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between z-10 shrink-0">
      {/* Left: Status Pill */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs font-medium">
          <span
            className={`w-2 h-2 rounded-full ${
              sseConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
            }`}
          />
          <span className="text-slate-300">
            {sseConnected ? 'Live Realtime Connected' : 'Connecting to Live Stream...'}
          </span>
        </div>
        <div className="hidden md:flex items-center space-x-1.5 text-xs text-slate-400">
          <Shield className="w-3.5 h-3.5 text-blue-400" />
          <span>Local Sovereign Mode</span>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-3">
        {/* Refresh */}
        <button
          onClick={onRefresh}
          className={`p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors ${
            isRefreshing ? 'animate-spin text-blue-400' : ''
          }`}
          title="Refresh dashboard data"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          title="Toggle color theme"
        >
          {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notifications Popover */}
        <div className="relative">
          <button
            onClick={() => setShowNotifMenu(!showNotifMenu)}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors relative"
            title="Notifications"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 bg-blue-500 rounded-full ring-2 ring-slate-900" />
            )}
          </button>

          {showNotifMenu && (
            <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-4 z-50">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <span className="font-semibold text-sm text-white">Notifications ({unreadCount} new)</span>
                {unreadCount > 0 && (
                  <button
                    onClick={() => {
                      onMarkAllRead();
                    }}
                    className="text-xs text-blue-400 hover:underline"
                  >
                    Mark all read
                  </button>
                )}
              </div>
              <div className="max-h-72 overflow-y-auto divide-y divide-slate-800/60 py-2">
                {notifications.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-500">
                    No notifications yet.
                  </div>
                ) : (
                  notifications.slice(0, 5).map((n) => (
                    <div key={n.id} className="py-2.5 px-1 hover:bg-slate-800/30 rounded-lg transition-colors">
                      <div className="flex items-center justify-between text-xs">
                        <span className={`font-semibold ${
                          n.severity === 'error' ? 'text-red-400' :
                          n.severity === 'warning' ? 'text-amber-400' :
                          n.severity === 'success' ? 'text-emerald-400' : 'text-blue-400'
                        }`}>
                          {n.title}
                        </span>
                        <span className="text-[10px] text-slate-500">{n.created_at.slice(11, 16)}</span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1 line-clamp-2">{n.message}</p>
                    </div>
                  ))
                )}
              </div>
              <div className="pt-2 border-t border-slate-800 text-center">
                <button
                  onClick={() => {
                    setShowNotifMenu(false);
                    onOpenNotificationsTab();
                  }}
                  className="text-xs text-blue-400 hover:text-blue-300 font-medium"
                >
                  View all notifications &rarr;
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Docs Link */}
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition-colors"
        >
          <span>Swagger API Docs</span>
          <ExternalLink className="w-3 h-3 text-slate-400" />
        </a>
      </div>
    </header>
  );
};

