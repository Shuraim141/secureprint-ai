import { useState } from "react";

import ErrorBanner from "../components/ErrorBanner";
import Panel from "../components/Panel";
import StatCard from "../components/StatCard";
import StatusBadge, { toneForStatus } from "../components/StatusBadge";
import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";

const HEALTH_ROWS = [
  ["api", "API"],
  ["database", "Database"],
  ["storage", "Encrypted storage"],
  ["ml", "ML service"],
];

function formatTime(value) {
  return new Date(value).toLocaleString();
}

export default function DashboardPage() {
  const { user, can } = useAuth();
  const canAudit = can("audit:view");
  const health = useResource((signal) => api.health(signal), { intervalMs: 10000 });
  const summary = useResource((signal) => api.dashboardSummary(signal), { intervalMs: 15000 });
  const audit = useResource((signal) => api.auditLogs({ limit: 8 }, signal), {
    enabled: canAudit,
    intervalMs: 15000,
  });
  const [verification, setVerification] = useState({ state: "idle", result: null, error: null });

  async function verifyChain() {
    setVerification({ state: "running", result: null, error: null });
    try {
      const result = await api.verifyAuditChain();
      setVerification({ state: "done", result, error: null });
      audit.reload();
    } catch (error) {
      setVerification({ state: "error", result: null, error });
    }
  }

  const s = summary.data;
  const cards = [
    ["Designs registered", s?.designs, "Phase 4"],
    ["Active prints", s?.active_prints, "Phase 7"],
    ["Defects detected", s?.defects_detected, "Phase 5"],
    ["Security incidents", s ? `${s.incidents_open} open / ${s.incidents_total}` : null, "Phase 7"],
    ["Parts registered", s?.parts, "Phase 6"],
    ["Supply-chain events", s?.supply_chain_events, "Phase 6"],
    ["Audit events", s?.audit_events, "live"],
    ["Compliance controls", s ? `${s.compliance.pass_count} pass / ${s.compliance.total}` : null, "Phase 9"],
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
        <p className="text-sm text-slate-400">
          Live counts from the backend database. Modules that are not built yet correctly show 0.
        </p>
      </div>

      <ErrorBanner error={summary.error} prefix="Could not load dashboard summary" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value, hint]) => (
          <StatCard
            key={label}
            label={label}
            value={value ?? "—"}
            hint={hint === "live" ? "recorded so far" : `module: ${hint}`}
            loading={summary.loading}
          />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="System health"
          action={
            health.data ? (
              <StatusBadge tone={toneForStatus(health.data.status)}>{health.data.status}</StatusBadge>
            ) : null
          }
        >
          <ErrorBanner error={health.error} prefix="Health check failed" />
          <ul className="divide-y divide-slate-800">
            {HEALTH_ROWS.map(([key, label]) => (
              <li key={key} className="flex items-center justify-between py-2 text-sm">
                <span className="text-slate-300">{label}</span>
                <StatusBadge tone={toneForStatus(health.data?.[key])}>
                  {health.data?.[key] ?? (health.loading ? "checking…" : "unknown")}
                </StatusBadge>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            “not_configured” means the ML models arrive in Phase 5; it is reported honestly, not faked.
          </p>
        </Panel>

        <Panel title="Your session">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-slate-400">User</dt><dd>{user.username}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-400">Role</dt><dd>{user.role}</dd></div>
          </dl>
          <div className="mt-3">
            <div className="mb-1 text-xs text-slate-400">Permissions granted by the backend</div>
            <div className="flex flex-wrap gap-1.5">
              {user.permissions.map((permission) => (
                <span key={permission} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                  {permission}
                </span>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      {canAudit ? (
        <Panel
          title="Recent audit events"
          action={
            <button
              type="button"
              onClick={verifyChain}
              disabled={verification.state === "running"}
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-60"
            >
              {verification.state === "running" ? "Verifying…" : "Verify audit chain"}
            </button>
          }
        >
          <ErrorBanner error={audit.error} prefix="Could not load audit log" />
          <ErrorBanner error={verification.error} prefix="Verification failed" />
          {verification.result ? (
            <div
              role="status"
              className={`mb-3 rounded-lg px-4 py-2 text-sm ${verification.result.valid ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}`}
            >
              {verification.result.valid
                ? `Chain intact: ${verification.result.checked} records verified.`
                : `INTEGRITY FAILURE at record #${verification.result.first_broken_id}: ${verification.result.reason}`}
            </div>
          ) : null}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">User</th>
                  <th className="py-2 pr-4">Action</th>
                  <th className="py-2 pr-4">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {(audit.data?.items ?? []).map((row) => (
                  <tr key={row.id}>
                    <td className="py-2 pr-4 text-slate-500">{row.id}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">{formatTime(row.timestamp)}</td>
                    <td className="py-2 pr-4">{row.user}</td>
                    <td className="py-2 pr-4">{row.action}</td>
                    <td className="py-2 pr-4">
                      <StatusBadge tone={row.result === "SUCCESS" ? "ok" : "error"}>{row.result}</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : (
        <Panel title="Recent audit events">
          <p className="text-sm text-slate-400">
            Your role ({user.role}) does not include audit access. Audit logs are visible to ADMIN and AUDITOR.
          </p>
        </Panel>
      )}
    </div>
  );
}
