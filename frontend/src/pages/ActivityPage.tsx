import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import {
  Activity, GitCommit, Cpu, Calendar, Upload, Download,
  CheckCircle2, AlertTriangle, XCircle, Filter, RefreshCw
} from 'lucide-react';

type EventKind = 'all' | 'commit' | 'dev_session' | 'sync' | 'validation';

const kindIcon: Record<string, React.ReactNode> = {
  commit: <GitCommit className="w-4 h-4 text-primary-500" />,
  dev_session: <Cpu className="w-4 h-4 text-violet-500" />,
  scheduler: <Calendar className="w-4 h-4 text-amber-500" />,
  fetch: <Download className="w-4 h-4 text-sky-500" />,
  push: <Upload className="w-4 h-4 text-emerald-500" />,
  validation: <CheckCircle2 className="w-4 h-4 text-teal-500" />,
  error: <XCircle className="w-4 h-4 text-red-500" />,
  warning: <AlertTriangle className="w-4 h-4 text-amber-500" />,
};

export const ActivityPage: React.FC = () => {
  const [events, setEvents] = useState<any[]>([]);
  const [filter, setFilter] = useState<EventKind>('all');
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 30;

  useEffect(() => {
    loadEvents();
  }, []);

  const loadEvents = async () => {
    setLoading(true);
    try {
      const activity = await api.getDashboardActivity(100);
      setEvents(activity);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const filtered = events.filter(e => {
    if (filter === 'all') return true;
    const kind = (e.event_type || e.kind || '').toLowerCase();
    if (filter === 'commit') return kind.includes('commit');
    if (filter === 'dev_session') return kind.includes('dev') || kind.includes('session');
    if (filter === 'sync') return kind.includes('fetch') || kind.includes('push') || kind.includes('sync');
    if (filter === 'validation') return kind.includes('valid') || kind.includes('scan') || kind.includes('secret');
    return true;
  });

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Activity Timeline</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Filterable event log for all commits, development sessions, syncs and validations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 p-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg">
            {(['all', 'commit', 'dev_session', 'sync', 'validation'] as EventKind[]).map(k => (
              <button
                key={k}
                onClick={() => { setFilter(k); setPage(1); }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filter === k
                    ? 'bg-primary-600 text-white'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                {k.replace('_', ' ')}
              </button>
            ))}
          </div>
          <button
            onClick={loadEvents}
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-500 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading activity...</div>
        ) : paginated.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <Activity className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>No activity recorded yet.</p>
          </div>
        ) : (
          <div className="relative">
            <div className="absolute left-8 top-0 bottom-0 w-px bg-slate-100 dark:bg-slate-700" />
            <div className="divide-y divide-slate-100 dark:divide-slate-700/40">
              {paginated.map((event, idx) => {
                const kind = (event.event_type || event.kind || 'activity').toLowerCase();
                const icon = kindIcon[kind] || kindIcon['commit'];
                const ts = event.timestamp || event.created_at || event.started_at;
                return (
                  <div key={idx} className="pl-16 pr-6 py-4 relative hover:bg-slate-50/60 dark:hover:bg-slate-700/20 transition-colors">
                    <div className="absolute left-5 top-4 w-6 h-6 rounded-full bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center">
                      {icon}
                    </div>
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                          {event.description || event.message || event.commit_message?.split('\n')[0] || `${kind} event`}
                        </p>
                        {event.repo_name && (
                          <p className="text-xs text-slate-500 mt-0.5">
                            Repo: <span className="font-medium text-slate-700 dark:text-slate-300">{event.repo_name}</span>
                          </p>
                        )}
                        {event.details && (
                          <p className="text-xs text-slate-400 mt-1 font-mono">{event.details}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          kind.includes('error') || kind.includes('fail') ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300' :
                          kind.includes('warn') ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' :
                          'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                        }`}>
                          {kind}
                        </span>
                        {ts && (
                          <span className="text-xs text-slate-400">
                            {new Date(ts).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between">
            <span className="text-xs text-slate-400">Page {page} of {totalPages} · {filtered.length} events</span>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1 text-xs rounded border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1 text-xs rounded border border-slate-200 dark:border-slate-700 disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
