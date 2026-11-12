import React, { useState } from 'react';
import {
  CalendarDays,
  Pause,
  Play,
  RotateCcw,
  CheckCircle2,
  Clock,
  AlertCircle,
  HelpCircle,
  AlertTriangle,
} from 'lucide-react';
import { WeeklySchedule, ScheduledSession } from '../types';
import { pauseScheduler, resumeScheduler, generateSchedule } from '../services/api';

interface SchedulerPageProps {
  schedule: WeeklySchedule | null;
  onRefresh: () => void;
}

export const SchedulerPage: React.FC<SchedulerPageProps> = ({
  schedule,
  onRefresh,
}) => {
  const [loading, setLoading] = useState(false);
  const [showConfirmRegen, setShowConfirmRegen] = useState(false);

  const daysOfWeek = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  const handleToggleActive = async () => {
    if (!schedule) return;
    setLoading(true);
    try {
      if (schedule.is_active) {
        await pauseScheduler();
      } else {
        await resumeScheduler();
      }
      onRefresh();
    } catch (e: any) {
      alert(`Error toggling scheduler: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleForceRegen = async () => {
    setLoading(true);
    try {
      await generateSchedule(true);
      setShowConfirmRegen(false);
      onRefresh();
    } catch (e: any) {
      alert(`Error generating schedule: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Build 7-day display list
  const sessionsByDay: { [day: number]: ScheduledSession } = {};
  if (schedule?.sessions) {
    schedule.sessions.forEach((s) => {
      sessionsByDay[s.day_of_week] = s;
    });
  }

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-6 rounded-2xl">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center space-x-2">
            <CalendarDays className="w-5 h-5 text-blue-400" />
            <span>Weekly 5-Day Random Scheduler</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Autonomous sessions run on exactly 5 randomly selected days per ISO week. Preserved across application restarts.
          </p>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <button
            onClick={handleToggleActive}
            disabled={loading}
            className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center space-x-2 transition-all shadow-md ${
              schedule?.is_active
                ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/30'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30'
            }`}
          >
            {schedule?.is_active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{schedule?.is_active ? 'Pause Scheduler' : 'Resume Scheduler'}</span>
          </button>

          <button
            onClick={() => setShowConfirmRegen(true)}
            disabled={loading}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold flex items-center space-x-2 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Regenerate Schedule</span>
          </button>
        </div>
      </div>

      {/* Week Metadata Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">ISO Week</span>
          <p className="text-lg font-bold text-white mt-1">{schedule?.week_identifier || 'N/A'}</p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Status</span>
          <p className={`text-lg font-bold mt-1 ${schedule?.is_active ? 'text-emerald-400' : 'text-amber-400'}`}>
            {schedule?.is_active ? 'ACTIVE' : 'PAUSED'}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Timezone</span>
          <p className="text-lg font-bold text-white mt-1">{schedule?.timezone || 'Asia/Kolkata'}</p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Scheduled Sessions</span>
          <p className="text-lg font-bold text-blue-400 mt-1">{schedule?.sessions?.length || 0} / 5 Days</p>
        </div>
      </div>

      {/* 7-Day Calendar Grid */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm">
        <h2 className="text-sm font-bold text-white mb-4">ISO Week Days Calendar</h2>
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          {daysOfWeek.map((dayName, idx) => {
            const session = sessionsByDay[idx];
            const isScheduled = !!session;

            return (
              <div
                key={idx}
                className={`rounded-2xl p-4 border flex flex-col justify-between min-h-[190px] transition-all ${
                  isScheduled
                    ? 'bg-gradient-to-b from-blue-950/40 to-slate-900 border-blue-500/40 shadow-lg shadow-blue-950/20'
                    : 'bg-slate-800/20 border-slate-800/80 opacity-60'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <span className="font-bold text-xs text-white">{dayName}</span>
                    <span className="text-[10px] font-mono text-slate-400">Day {idx + 1}</span>
                  </div>

                  {isScheduled ? (
                    <div className="mt-3 space-y-2">
                      <div className="text-xs font-mono text-blue-400 font-semibold">
                        {session.scheduled_date}
                      </div>
                      <div className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-900/60 border border-blue-700/60 text-[10px] font-mono text-blue-200">
                        <Clock className="w-3 h-3 text-blue-300" />
                        <span>{session.time_window}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-8 text-center text-[11px] text-slate-500 font-medium">
                      Off Day (Inactive)
                    </div>
                  )}
                </div>

                {isScheduled && (
                  <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[10px]">
                    <span className={`px-2 py-0.5 rounded font-bold uppercase ${
                      session.status === 'completed'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : session.status === 'missed'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : 'bg-slate-800 text-blue-300 border border-slate-700'
                    }`}>
                      {session.status}
                    </span>
                    {session.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Confirmation Modal for Force Regenerate */}
      {showConfirmRegen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center space-x-2 text-amber-400 mb-2">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <h3 className="font-bold text-sm text-white">Regenerate Weekly Schedule?</h3>
            </div>
            <p className="text-xs text-slate-300 mt-2 leading-relaxed">
              AutoGit AI persists schedules across restarts. Force-regenerating will discard the current 5 scheduled days and generate a new set of 5 random days. Are you sure you wish to proceed?
            </p>
            <div className="flex items-center justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowConfirmRegen(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleForceRegen}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all"
              >
                Regenerate Now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

