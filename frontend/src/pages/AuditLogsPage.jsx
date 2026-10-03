import { useState } from "react";

import ErrorBanner from "../components/ErrorBanner";
import Panel from "../components/Panel";
import StatusBadge from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";
import { shortHash } from "../utils/format";

const PAGE_SIZE = 25;
const SEVERITY_TONE = { INFO: "neutral", WARNING: "warn", HIGH: "error", CRITICAL: "error" };

export default function AuditLogsPage() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState("");
  const [severity, setSeverity] = useState("");
  const [offset, setOffset] = useState(0);
  const [chain, setChain] = useState(null);
  const [chainError, setChainError] = useState(null);

  const params = { q: q || undefined, result: result || undefined, severity: severity || undefined,
    limit: PAGE_SIZE, offset };
  const { data, error, loading } = useResource((signal) => api.auditLogs(params, signal), {
    deps: [q, result, severity, offset],
  });

  async function verifyChain() {
    setChainError(null);
    try {
      setChain(await api.verifyAuditChain());
    } catch (err) {
      setChainError(err);
    }
  }

  const change = (setter) => (event) => {
    setter(event.target.value);
    setOffset(0);
  };
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Logs</h1>
          <p className="text-sm text-slate-400">Tamper-evident, hash-chained record of security events.</p>
        </div>
        <button type="button" onClick={verifyChain}
          className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400">
          Verify chain
        </button>
      </header>

      <ErrorBanner error={chainError} prefix="Could not verify chain" />
      {chain && (
        <div role="status" className={`rounded-lg border px-4 py-3 text-sm ${chain.valid
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
          {chain.valid
            ? `Audit chain intact: ${chain.checked} entries verified.`
            : `INTEGRITY FAILURE at entry #${chain.first_broken_id}: ${chain.reason}`}
        </div>
      )}

      <Panel title="Filters">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm text-slate-300">Search
            <input value={q} onChange={change(setQ)} maxLength={100} placeholder="user, action or resource"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500" />
          </label>
          <label className="text-sm text-slate-300">Result
            <select value={result} onChange={change(setResult)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100">
              <option value="">All</option>
              <option value="SUCCESS">Success</option>
              <option value="FAILURE">Failure</option>
            </select>
          </label>
          <label className="text-sm text-slate-300">Severity
            <select value={severity} onChange={change(setSeverity)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100">
              <option value="">All</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="HIGH">High</option>
            </select>
          </label>
        </div>
      </Panel>

      <ErrorBanner error={error} prefix="Could not load audit logs" />
      <Panel title={`Entries (${total})`}>
        {loading && !data && <p className="text-sm text-slate-400">Loading…</p>}
        {data && data.items.length === 0 && <p className="text-sm text-slate-400">No entries match.</p>}
        {data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr><th className="py-2 pr-4">#</th><th className="pr-4">Time</th><th className="pr-4">User</th>
                  <th className="pr-4">Action</th><th className="pr-4">Resource</th><th className="pr-4">Result</th>
                  <th className="pr-4">Severity</th><th>Hash</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-slate-300">
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="py-2 pr-4 text-slate-500">{row.id}</td>
                    <td className="pr-4 whitespace-nowrap">{new Date(row.timestamp).toLocaleString()}</td>
                    <td className="pr-4">{row.user}</td>
                    <td className="pr-4 font-mono text-xs">{row.action}</td>
                    <td className="pr-4">{row.resource ?? "—"}</td>
                    <td className="pr-4">{row.result}</td>
                    <td className="pr-4"><StatusBadge tone={SEVERITY_TONE[row.severity] ?? "neutral"}>{row.severity}</StatusBadge></td>
                    <td className="font-mono text-xs text-slate-500" title={row.event_hash}>{shortHash(row.event_hash, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-lg border border-slate-700 px-3 py-1 disabled:opacity-40">Previous</button>
          <span>{total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
          <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-lg border border-slate-700 px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </Panel>
    </div>
  );
}
