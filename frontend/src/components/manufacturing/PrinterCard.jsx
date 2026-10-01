import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import { useResource } from "../../hooks/useResource";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { api } from "../../services/api";
import TelemetryChart from "./TelemetryChart";

const SCENARIOS = ["NORMAL", "OVERHEAT", "SPEED_SPIKE", "PARAMETER_TAMPERING"];
const STATE_TONE = { RUNNING: "ok", PAUSED: "error", COMPLETED: "neutral", IDLE: "neutral", ERROR: "error" };

export default function PrinterCard({ printer, canControl, onChanged }) {
  const [scenario, setScenario] = useState("NORMAL");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const telemetry = useResource((signal) => api.getTelemetry(printer.id, 40, signal), {
    intervalMs: 1000, deps: [printer.id, printer.simulator_state],
  });

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      if (action === "start") await api.startPrint(printer.id, scenario);
      else if (action === "pause") await api.pausePrint(printer.id);
      else await api.stopPrint(printer.id);
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  const samples = telemetry.data?.samples ?? [];
  const latest = samples[samples.length - 1];
  const idle = printer.simulator_state === "IDLE" || printer.simulator_state === "COMPLETED";

  return (
    <Panel
      title={`${printer.printer_code} · ${printer.name}`}
      action={<StatusBadge tone={STATE_TONE[printer.simulator_state] ?? "neutral"}>{printer.simulator_state}</StatusBadge>}
    >
      <ErrorBanner error={error} />
      {canControl ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            disabled={!idle}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 disabled:opacity-50"
          >
            {SCENARIOS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <button type="button" onClick={() => run("start")} disabled={busy || !idle}
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50">
            Start
          </button>
          <button type="button" onClick={() => run("pause")}
            disabled={busy || printer.simulator_state !== "RUNNING"}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50">
            Pause
          </button>
          <button type="button" onClick={() => run("stop")} disabled={busy || idle}
            className="rounded-lg border border-red-900 px-3 py-1.5 text-xs text-red-300 hover:bg-red-950 disabled:opacity-50">
            Stop
          </button>
        </div>
      ) : null}

      {latest ? (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Nozzle", `${latest.temperature.toFixed(1)}°C`],
              ["Bed", `${latest.bed_temperature.toFixed(1)}°C`],
              ["Speed", `${latest.speed.toFixed(0)} mm/s`],
              ["Flow", `${latest.flow_rate.toFixed(0)}%`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-slate-800 px-2 py-1.5 text-xs">
                <div className="text-slate-500">{label}</div>
                <div className="text-sm font-medium text-slate-100">{value}</div>
              </div>
            ))}
          </div>
          <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
            <span>
              Layer {latest.layer}/{latest.total_layers} · {latest.progress}% complete
            </span>
            {latest.anomaly ? <StatusBadge tone="error">ANOMALY: {latest.risk}</StatusBadge> : null}
          </div>
          <TelemetryChart samples={samples} />
        </>
      ) : (
        <p className="text-sm text-slate-500">No print running. Start one to see live telemetry.</p>
      )}
    </Panel>
  );
}
