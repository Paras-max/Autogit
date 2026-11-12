import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Notification } from '../types';
import {
  Bell, BellOff, CheckCheck, Info, AlertTriangle, Zap,
  GitCommit, Cpu, RefreshCw, Trash2
} from 'lucide-react';

const kindIcon: Record<string, React.ReactNode> = {
  commit: <GitCommit className="w-4 h-4 text-primary-500" />,
  dev_session: <Cpu className="w-4 h-4 text-violet-500" />,
  github_sync: <Zap className="w-4 h-4 text-amber-500" />,
  validation: <AlertTriangle className="w-4 h-4 text-orange-500" />,
  info: <Info className="w-4 h-4 text-sky-500" />,
  success: <CheckCheck className="w-4 h-4 text-emerald-500" />,
  error: <AlertTriangle className="w-4 h-4 text-red-500" />,
};

export const NotificationsPage: React.FC = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    loadNotifications();
  }, []);

  const loadNotifications = async () => {
    setLoading(true);
    try {
      const data = await api.getNotifications(50, false);
      setNotifications(data);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  const markRead = async (notifId: string) => {
    try {
      await api.markNotificationRead(notifId);
      setNotifications(n => n.map(x => x.notification_id === notifId ? { ...x, read: true } : x));
    } catch {}
  };

  const markAllRead = async () => {
    setMarkingAll(true);
    try {
      await api.markAllNotificationsRead();
      setNotifications(n => n.map(x => ({ ...x, read: true })));
    } catch {} finally {
      setMarkingAll(false);
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Bell className="w-6 h-6 text-primary-500" />
            Notifications
            {unreadCount > 0 && (
              <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold bg-primary-500 text-white rounded-full">
                {unreadCount}
              </span>
            )}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            System alerts for commits, development sessions, GitHub sync and validation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              onClick={markAllRead}
              disabled={markingAll}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              {markingAll ? 'Marking…' : 'Mark all read'}
            </button>
          )}
          <button
            onClick={loadNotifications}
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading notifications...</div>
        ) : notifications.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <BellOff className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p className="font-medium text-slate-600 dark:text-slate-300">No notifications yet</p>
            <p className="text-xs mt-1">System events like commits, dev sessions, and sync results will appear here.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
            {notifications.map((notif) => {
              const kind = (notif.notification_type || notif.kind || 'info').toLowerCase();
              const icon = kindIcon[kind] || kindIcon['info'];
              return (
                <div
                  key={notif.notification_id}
                  className={`px-6 py-4 flex items-start gap-4 transition-colors ${
                    !notif.read ? 'bg-primary-50/40 dark:bg-primary-950/20' : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'
                  }`}
                >
                  <div className={`mt-0.5 p-2 rounded-full ${
                    !notif.read ? 'bg-primary-100 dark:bg-primary-900/40' : 'bg-slate-100 dark:bg-slate-700'
                  }`}>
                    {icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className={`text-sm ${!notif.read ? 'font-semibold text-slate-900 dark:text-slate-100' : 'font-medium text-slate-700 dark:text-slate-300'}`}>
                          {notif.title}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
                          {notif.message}
                        </p>
                        {notif.repo_name && (
                          <span className="inline-block mt-1.5 text-xs px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full">
                            {notif.repo_name}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <span className="text-xs text-slate-400 whitespace-nowrap">
                          {new Date(notif.created_at || Date.now()).toLocaleString()}
                        </span>
                        {!notif.read && (
                          <button
                            onClick={() => markRead(notif.notification_id)}
                            className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium"
                          >
                            Mark read
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
