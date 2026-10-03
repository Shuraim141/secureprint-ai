import { useState } from "react";

import ErrorBanner from "../components/ErrorBanner";
import Panel from "../components/Panel";
import StatusBadge from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";

const TONE = { PASS: "ok", FAIL: "error", UNKNOWN: "warn" };
const FRAMEWORK_NAMES = { NIST: "NIST CSF", ISO9001: "ISO 9001", ISO_ASTM_52900: "ISO/ASTM 52900" };

export default function CompliancePage() {
  const { data, error, loading, reload } = useResource((signal) => api.complianceControls(signal));
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [fresh, setFresh] = useState(null);

  const report = fresh ?? data;

  async function runChecks() {
    setRunning(true);
    setRunError(null);
    try {
      setFresh(await api.runCompliance());
    } catch (err) {
      setRunError(err);
    } finally {
      setRunning(false);
    }
  }

  const groups = {};
  for (const control of report?.controls ?? []) {
    (groups[control.framework] ??= []).push(control);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Compliance</h1>
          <p className="text-sm text-slate-400">
            Automated technical checks against the live system, mapped to control references.
          </p>
        </div>
        <button
          type="button"
          onClick={runChecks}
          disabled={running}
          className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400 disabled:opacity-50"
        >
          {running ? "Running checks…" : "Run checks now"}
        </button>
      </header>

      <ErrorBanner error={error} prefix="Could not load compliance data" />
      <ErrorBanner error={runError} prefix="Could not run checks" />
      {loading && !report && <p className="text-sm text-slate-400">Loading…</p>}

      {report && (
        <>
          <div className="flex flex-wrap gap-3" aria-label="Compliance summary">
            <StatusBadge tone="ok">{report.pass_count} passing</StatusBadge>
            <StatusBadge tone="error">{report.fail_count} failing</StatusBadge>
            <StatusBadge tone="warn">{report.unknown_count} not yet verifiable</StatusBadge>
          </div>
          <p role="note" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            {report.disclaimer}
          </p>
          {report.total === 0 && (
            <p className="text-sm text-slate-400">
              No results stored yet. Click “Run checks now” to evaluate the system.
            </p>
          )}
          {Object.entries(groups).map(([framework, controls]) => (
            <Panel key={framework} title={FRAMEWORK_NAMES[framework] ?? framework}>
              <ul className="divide-y divide-slate-800">
                {controls.map((control) => (
                  <li key={control.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-slate-100">
                        <span className="mr-2 font-mono text-xs text-slate-500">{control.control_ref}</span>
                        {control.title}
                      </div>
                      <div className="text-xs text-slate-400">{control.description}</div>
                      <div className="mt-1 text-xs text-slate-300">Evidence: {control.evidence ?? "—"}</div>
                    </div>
                    <StatusBadge tone={TONE[control.status] ?? "neutral"}>{control.status}</StatusBadge>
                  </li>
                ))}
              </ul>
            </Panel>
          ))}
          <button type="button" onClick={reload} className="text-xs text-slate-500 hover:text-slate-300">
            Reload stored results
          </button>
        </>
      )}
    </div>
  );
}
