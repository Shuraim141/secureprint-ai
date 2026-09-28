import { useRef, useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";

const SEVERITY_TONE = { none: "ok", low: "warn", medium: "warn", high: "error" };

function ResultPanel({ result }) {
  const tone = SEVERITY_TONE[result.severity] ?? "neutral";
  return (
    <div className="mt-4 space-y-3 border-t border-slate-800 pt-4" data-testid="inspect-result">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge tone={result.status === "normal" ? "ok" : "error"}>
          {result.status === "normal" ? "NORMAL" : "DEFECT DETECTED"}
        </StatusBadge>
        <span className="text-sm text-slate-200">
          {result.defect_type} · confidence {(result.confidence * 100).toFixed(1)}%
        </span>
        <StatusBadge tone={tone}>severity: {result.severity}</StatusBadge>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {Object.entries(result.class_probabilities)
          .sort((a, b) => b[1] - a[1])
          .map(([cls, prob]) => (
            <div key={cls} className="rounded-lg border border-slate-800 px-2 py-1.5 text-xs">
              <div className="text-slate-400">{cls}</div>
              <div className="text-slate-100">{(prob * 100).toFixed(1)}%</div>
            </div>
          ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <figure>
          <img
            alt="Preprocessed"
            className="w-full rounded-lg border border-slate-800"
            src={`data:image/png;base64,${result.cv_report.original_png_base64}`}
          />
          <figcaption className="mt-1 text-center text-xs text-slate-500">Preprocessed</figcaption>
        </figure>
        <figure>
          <img
            alt="Canny edges"
            className="w-full rounded-lg border border-slate-800"
            src={`data:image/png;base64,${result.cv_report.edges_png_base64}`}
          />
          <figcaption className="mt-1 text-center text-xs text-slate-500">Edge detection</figcaption>
        </figure>
        <figure>
          <img
            alt="Detected contours"
            className="w-full rounded-lg border border-slate-800"
            src={`data:image/png;base64,${result.cv_report.contours_png_base64}`}
          />
          <figcaption className="mt-1 text-center text-xs text-slate-500">Contours</figcaption>
        </figure>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-slate-400 sm:grid-cols-4">
        <div>Edge density: <span className="text-slate-200">{result.cv_report.edge_density}</span></div>
        <div>Sharpness: <span className="text-slate-200">{result.cv_report.sharpness_variance}</span></div>
        <div>Contours: <span className="text-slate-200">{result.cv_report.contour_count}</span></div>
        <div>Model: <span className="text-slate-200">{result.model_version}</span></div>
      </dl>
      {result.cv_report.quality_flags.length > 0 ? (
        <ul className="list-inside list-disc text-xs text-amber-300">
          {result.cv_report.quality_flags.map((flag) => (
            <li key={flag}>{flag}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function InspectCard({ onInspected, api }) {
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
      const outcome = await api.inspectImage(file);
      setResult(outcome);
      onInspected?.(outcome);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="AI quality inspection">
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorBanner error={error} prefix="Inspection failed" />
        <label className="block text-sm text-slate-300">
          Print / manufacturing image
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg"
            required
            className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-200"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
        >
          {busy ? "Running CV pipeline + classifier…" : "Inspect image"}
        </button>
      </form>
      {result ? <ResultPanel result={result} /> : null}
    </Panel>
  );
}
