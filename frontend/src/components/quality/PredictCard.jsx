import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";

const FIELDS = [
  ["nozzle_temp_c", "Nozzle temperature (°C)"],
  ["bed_temp_c", "Bed temperature (°C)"],
  ["speed_mm_s", "Print speed (mm/s)"],
  ["layer_height_mm", "Layer height (mm)"],
  ["extrusion_rate_pct", "Extrusion rate (%)"],
  ["duration_min", "Print duration (min)"],
];

const PRESETS = {
  NORMAL: { nozzle_temp_c: "205", bed_temp_c: "60", speed_mm_s: "50",
           layer_height_mm: "0.2", extrusion_rate_pct: "100", duration_min: "60" },
  SUSPICIOUS: { nozzle_temp_c: "280", bed_temp_c: "100", speed_mm_s: "250",
               layer_height_mm: "0.2", extrusion_rate_pct: "100", duration_min: "60" },
};

const RISK_TONE = { LOW: "ok", MEDIUM: "warn", HIGH: "error" };

export default function PredictCard({ api }) {
  const [values, setValues] = useState(PRESETS.NORMAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const set = (key) => (event) => setValues((prev) => ({ ...prev, [key]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v)]));
      setResult(await api.predictProcessQuality(body));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Predictive quality analytics"
      action={
        <div className="flex gap-1">
          <button type="button" onClick={() => setValues(PRESETS.NORMAL)}
            className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">
            Load NORMAL
          </button>
          <button type="button" onClick={() => setValues(PRESETS.SUSPICIOUS)}
            className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">
            Load SUSPICIOUS
          </button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
        <ErrorBanner error={error} />
        {FIELDS.map(([key, label]) => (
          <label key={key} className="text-xs text-slate-300">
            {label}
            <input
              type="number" step="any" required value={values[key]} onChange={set(key)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
            />
          </label>
        ))}
        <div className="sm:col-span-2">
          <button type="submit" disabled={busy}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60">
            {busy ? "Predicting…" : "Predict quality"}
          </button>
        </div>
      </form>
      {result ? (
        <div className="mt-4 space-y-2 border-t border-slate-800 pt-4" data-testid="predict-result">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge tone={result.predicted_quality === "good" ? "ok" : result.predicted_quality === "fair" ? "warn" : "error"}>
              predicted: {result.predicted_quality}
            </StatusBadge>
            <StatusBadge tone={RISK_TONE[result.risk_level]}>risk: {result.risk_level}</StatusBadge>
            <StatusBadge tone={result.is_anomaly ? "error" : "ok"}>
              anomaly score {result.anomaly_score}
            </StatusBadge>
          </div>
          {Object.keys(result.out_of_range_parameters).length > 0 ? (
            <ul className="list-inside list-disc text-sm text-amber-300">
              {Object.entries(result.out_of_range_parameters).map(([name, info]) => (
                <li key={name}>
                  {name} = {info.value} (safe range {info.safe_range[0]}–{info.safe_range[1]})
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-emerald-300">All parameters within the safe operating range.</p>
          )}
        </div>
      ) : null}
    </Panel>
  );
}
