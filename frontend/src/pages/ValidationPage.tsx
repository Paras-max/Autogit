import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import {
  Shield, AlertTriangle, CheckCircle2, XCircle, Eye, EyeOff,
  FileSearch, Lock, FlaskConical, ChevronDown, ChevronRight, Info
} from 'lucide-react';

interface PolicyRule {
  rule_id: string;
  name: string;
  description: string;
  enabled: boolean;
  severity: 'low' | 'medium' | 'high' | 'critical';
}

const DEFAULT_POLICIES: PolicyRule[] = [
  { rule_id: 'no_secrets', name: 'Secret Detection', description: 'Block commits containing API keys, tokens, passwords or private keys.', enabled: true, severity: 'critical' },
  { rule_id: 'no_binary', name: 'Binary File Guard', description: 'Warn before committing large binary files.', enabled: true, severity: 'medium' },
  { rule_id: 'conventional_commits', name: 'Conventional Commits', description: 'Enforce conventional commit message format (feat, fix, chore…).', enabled: true, severity: 'low' },
  { rule_id: 'max_file_size', name: 'Max File Size', description: 'Block files exceeding 10 MB from being committed.', enabled: true, severity: 'high' },
  { rule_id: 'no_force_push', name: 'No Force Push', description: 'Prevent force-push operations on any branch.', enabled: true, severity: 'critical' },
  { rule_id: 'approval_required', name: 'Approval Gate', description: 'Require explicit user approval before committing in Smart Commit mode.', enabled: true, severity: 'high' },
  { rule_id: 'no_merge_rebase', name: 'No Auto Merge/Rebase', description: 'Never auto-merge or auto-rebase; halt and request user intervention on divergence.', enabled: true, severity: 'critical' },
];

const severityColors: Record<string, string> = {
  low: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

export const ValidationPage: React.FC = () => {
  const [policies, setPolicies] = useState<PolicyRule[]>(DEFAULT_POLICIES);
  const [scanResults, setScanResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadScanHistory();
  }, []);

  const loadScanHistory = async () => {
    setLoading(true);
    try {
      const history = await api.getExecutionHistory(undefined, 20);
      const scans = history.filter((h: any) => h.validation_result || h.secret_scan_result);
      setScanResults(scans);
    } catch {
      setScanResults([]);
    } finally {
      setLoading(false);
    }
  };

  const togglePolicy = (rule_id: string) => {
    // Local UI toggle only – persisted on backend via settings in a full implementation
    setPolicies(p => p.map(r => r.rule_id === rule_id ? { ...r, enabled: !r.enabled } : r));
  };

  const toggleExpand = (id: string) => {
    setExpanded(p => ({ ...p, [id]: !p[id] }));
  };

  const enabledCount = policies.filter(p => p.enabled).length;
  const criticalCount = policies.filter(p => p.severity === 'critical' && p.enabled).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Validation & Security</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Manage commit policies, review secret scan results, and inspect validation history.
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Active Policies', value: enabledCount, icon: Shield, color: 'text-primary-500' },
          { label: 'Critical Rules', value: criticalCount, icon: Lock, color: 'text-red-500' },
          { label: 'Scan Records', value: scanResults.length, icon: FileSearch, color: 'text-amber-500' },
          { label: 'Total Rules', value: policies.length, icon: FlaskConical, color: 'text-emerald-500' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 flex items-center gap-3">
            <Icon className={`w-6 h-6 ${color}`} />
            <div>
              <p className="text-xs text-slate-500">{label}</p>
              <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Policy Rules */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary-500" /> Security Policies
          </h2>
          <span className="text-xs text-slate-400">
            {enabledCount}/{policies.length} active
          </span>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
          {policies.map((rule) => (
            <div key={rule.rule_id} className="px-6 py-4 flex items-center justify-between gap-4">
              <div className="flex items-start gap-3 min-w-0">
                <div className={`mt-0.5 ${rule.enabled ? 'text-emerald-500' : 'text-slate-300 dark:text-slate-600'}`}>
                  {rule.enabled ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-white">{rule.name}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{rule.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${severityColors[rule.severity]}`}>
                  {rule.severity}
                </span>
                <button
                  onClick={() => togglePolicy(rule.rule_id)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${rule.enabled ? 'bg-primary-500' : 'bg-slate-300 dark:bg-slate-600'}`}
                >
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transform transition-transform ${rule.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scan History */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <FileSearch className="w-4 h-4 text-amber-500" /> Secret Scan & Validation History
          </h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading scan records…</div>
        ) : scanResults.length === 0 ? (
          <div className="p-8 text-center text-slate-400">
            <Shield className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>No validation records yet. Run a commit or development session to generate scan results.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
            {scanResults.map((result, idx) => {
              const passed = result.validation_result?.passed !== false;
              const secrets = result.secret_scan_result?.secrets_found?.length || 0;
              return (
                <div key={idx}>
                  <button
                    onClick={() => toggleExpand(String(idx))}
                    className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-700/40 transition-colors text-left"
                  >
                    <div className="flex items-center gap-3">
                      {passed && secrets === 0 ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                      )}
                      <div>
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {result.repo_name || 'Unknown Repo'} — {new Date(result.timestamp || Date.now()).toLocaleString()}
                        </p>
                        <p className="text-xs text-slate-500">
                          {passed ? 'Validation passed' : 'Validation failed'} · {secrets > 0 ? `${secrets} secret(s) detected` : 'No secrets found'}
                        </p>
                      </div>
                    </div>
                    {expanded[String(idx)] ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                  </button>
                  {expanded[String(idx)] && (
                    <div className="px-6 pb-4 space-y-2">
                      {result.validation_result && (
                        <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs font-mono text-slate-700 dark:text-slate-300 overflow-x-auto">
                          {JSON.stringify(result.validation_result, null, 2)}
                        </pre>
                      )}
                      {result.secret_scan_result && (
                        <pre className="p-3 bg-red-50 dark:bg-red-950/20 rounded-lg text-xs font-mono text-red-700 dark:text-red-300 overflow-x-auto">
                          {JSON.stringify(result.secret_scan_result, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
