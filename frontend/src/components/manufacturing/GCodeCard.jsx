import { useRef, useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { api } from "../../services/api";

const RISK_TONE = { NONE: "ok", LOW: "warn", MEDIUM: "warn", HIGH: "error" };

export default function GCodeCard() {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.analyzeGcode(file));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="G-code security analysis">
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorBanner error={error} />
        <input
          ref={fileRef}
          type="file"
          accept=".gcode,.gco,.g,.nc,.txt"
          required
          className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-200"
        />
        <button type="submit" disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60">
          {busy ? "Analyzing…" : "Analyze G-code"}
        </button>
      </form>
      {result ? (
        <div className="mt-4 space-y-3 border-t border-slate-800 pt-4" data-testid="gcode-result">
          <div className="flex items-center gap-3">
            <StatusBadge tone={result.safe ? "ok" : "error"}>{result.safe ? "SAFE" : "SECURITY WARNING"}</StatusBadge>
            <StatusBadge tone={RISK_TONE[result.risk] ?? "neutral"}>risk: {result.risk}</StatusBadge>
          </div>
          {result.findings.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {result.findings.map((finding, index) => (
                <li key={index} className="rounded-lg border border-slate-800 px-3 py-1.5">
                  <span className="text-slate-500">line {finding.line || "—"}</span>{" "}
                  <StatusBadge tone={RISK_TONE[finding.severity] ?? "neutral"}>{finding.severity}</StatusBadge>{" "}
                  <code className="text-xs text-slate-500">{finding.code}</code>
                  <div className="text-slate-300">{finding.message}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-emerald-300">No findings. File parses cleanly.</p>
          )}
          <dl className="grid grid-cols-2 gap-2 text-xs text-slate-400 sm:grid-cols-4">
            <div>Lines: <span className="text-slate-200">{result.stats.total_lines}</span></div>
            <div>Moves: <span className="text-slate-200">{result.stats.move_commands}</span></div>
            <div>Max nozzle: <span className="text-slate-200">{result.stats.max_nozzle_temp_c ?? "—"}°C</span></div>
            <div>Max feed: <span className="text-slate-200">{result.stats.max_feed_rate_mm_s ?? "—"} mm/s</span></div>
          </dl>
        </div>
      ) : null}
    </Panel>
  );
}
