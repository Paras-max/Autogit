import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import {
  Settings, Server, KeyRound, User, GitBranch, Cpu,
  CheckCircle2, XCircle, AlertCircle, RefreshCw, Play,
  Square, RotateCcw, Eye, EyeOff, Save
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [serviceStatus, setServiceStatus] = useState<any>(null);
  const [healthData, setHealthData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // AI Settings state (local form)
  const [aiProvider, setAiProvider] = useState('google');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [model, setModel] = useState('gemini-2.0-flash');

  // Git Identity state
  const [gitName, setGitName] = useState('');
  const [gitEmail, setGitEmail] = useState('');
  const [savingGit, setSavingGit] = useState(false);
  const [savingAI, setSavingAI] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [svc, health] = await Promise.all([
        api.getServiceStatus(),
        api.getHealthStatus(),
      ]);
      setServiceStatus(svc);
      setHealthData(health);
    } catch {
      setServiceStatus(null);
      setHealthData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleServiceAction = async (action: 'start' | 'stop' | 'restart') => {
    setActionMsg(null);
    try {
      const result = await api.serviceAction(action);
      setActionMsg({ type: 'success', text: result.message || `Service ${action}ed.` });
      setTimeout(loadAll, 1200);
    } catch (err: any) {
      setActionMsg({ type: 'error', text: err?.message || `Failed to ${action} service.` });
    }
  };

  const saveAISettings = async () => {
    setSavingAI(true);
    try {
      await api.updateAISettings({ provider: aiProvider, api_key: apiKey, model });
      setActionMsg({ type: 'success', text: 'AI settings saved.' });
    } catch (err: any) {
      setActionMsg({ type: 'error', text: err?.message || 'Failed to save AI settings.' });
    } finally {
      setSavingAI(false);
    }
  };

  const saveGitIdentity = async () => {
    setSavingGit(true);
    try {
      await api.updateGitIdentity({ name: gitName, email: gitEmail });
      setActionMsg({ type: 'success', text: 'Git identity updated.' });
    } catch (err: any) {
      setActionMsg({ type: 'error', text: err?.message || 'Failed to update git identity.' });
    } finally {
      setSavingGit(false);
    }
  };

  const healthChecks = healthData?.checks || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Settings className="w-6 h-6 text-primary-500" /> Settings
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Background service controls, AI provider configuration, and Git identity settings.
        </p>
      </div>

      {actionMsg && (
        <div className={`flex items-center gap-2 text-sm p-4 rounded-xl ${
          actionMsg.type === 'success'
            ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
            : 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
        }`}>
          {actionMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <XCircle className="w-4 h-4 shrink-0" />}
          {actionMsg.text}
        </div>
      )}

      {/* Background Service */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Server className="w-4 h-4 text-primary-500" /> Background Service
          </h2>
          <button onClick={loadAll} className="text-xs text-slate-400 hover:text-primary-600 flex items-center gap-1">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="text-sm text-slate-500">Loading service status...</div>
        ) : (
          <>
            <div className="flex items-center gap-4 flex-wrap">
              <span className={`inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1 rounded-full ${
                serviceStatus?.status === 'running'
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
              }`}>
                {serviceStatus?.status === 'running' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                {serviceStatus?.status || 'Unknown'}
              </span>
              {serviceStatus?.uptime && (
                <span className="text-xs text-slate-500">Uptime: {serviceStatus.uptime}</span>
              )}
              {serviceStatus?.pid && (
                <span className="text-xs text-slate-500 font-mono">PID: {serviceStatus.pid}</span>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => handleServiceAction('start')}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
              >
                <Play className="w-3.5 h-3.5" /> Start
              </button>
              <button
                onClick={() => handleServiceAction('stop')}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
              >
                <Square className="w-3.5 h-3.5" /> Stop
              </button>
              <button
                onClick={() => handleServiceAction('restart')}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Restart
              </button>
            </div>

            {/* Health Checks */}
            {Object.keys(healthChecks).length > 0 && (
              <div className="mt-2 space-y-2">
                <p className="text-xs font-semibold text-slate-500 uppercase">Health Checks</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {Object.entries(healthChecks).map(([key, val]: [string, any]) => (
                    <div key={key} className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                      {val === true || val === 'ok' || val === 'healthy'
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        : <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0" />}
                      <span className="text-xs text-slate-700 dark:text-slate-300 capitalize">{key.replace(/_/g, ' ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* AI Provider Settings */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-5 space-y-4">
        <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <Cpu className="w-4 h-4 text-violet-500" /> AI Provider
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1">
              Provider
            </label>
            <select
              value={aiProvider}
              onChange={(e) => setAiProvider(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="google">Google (Gemini)</option>
              <option value="openai">OpenAI (GPT)</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="ollama">Ollama (Local)</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Model</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gemini-2.0-flash"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1">
            <KeyRound className="w-3.5 h-3.5" /> API Key
          </label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Paste your API key (stored encrypted in .env)"
              className="w-full px-3 py-2 pr-10 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono"
            />
            <button
              onClick={() => setShowKey(s => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
        <button
          onClick={saveAISettings}
          disabled={savingAI}
          className="inline-flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          <Save className="w-4 h-4" /> {savingAI ? 'Saving…' : 'Save AI Settings'}
        </button>
      </div>

      {/* Git Identity */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-5 space-y-4">
        <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-amber-500" /> Git Identity
        </h2>
        <p className="text-xs text-slate-500">
          Used as author attribution for AI-generated commits. Leave blank to use the global Git config.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1">
              <User className="w-3.5 h-3.5" /> Author Name
            </label>
            <input
              type="text"
              value={gitName}
              onChange={(e) => setGitName(e.target.value)}
              placeholder="e.g. AutoGit AI"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Author Email</label>
            <input
              type="email"
              value={gitEmail}
              onChange={(e) => setGitEmail(e.target.value)}
              placeholder="e.g. autogit@yourdomain.com"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>
        <button
          onClick={saveGitIdentity}
          disabled={savingGit}
          className="inline-flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
        >
          <Save className="w-4 h-4" /> {savingGit ? 'Saving…' : 'Save Git Identity'}
        </button>
      </div>
    </div>
  );
};
