import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";

export default function CreatePartCard({ designs, onCreated }) {
  const [designId, setDesignId] = useState("");
  const [batch, setBatch] = useState("BATCH-001");
  const [material, setMaterial] = useState("PLA");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!designId) return;
    setBusy(true);
    setError(null);
    try {
      const part = await onCreated(Number(designId), batch, material);
      if (part) setBatch("BATCH-001");
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Create a manufactured part">
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-3">
        <ErrorBanner error={error} />
        <label className="text-xs text-slate-300 sm:col-span-1">
          Design
          <select
            value={designId}
            onChange={(e) => setDesignId(e.target.value)}
            required
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
          >
            <option value="">Select a registered design…</option>
            {designs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.design_code} · {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-300">
          Batch
          <input value={batch} onChange={(e) => setBatch(e.target.value)} required
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100" />
        </label>
        <label className="text-xs text-slate-300">
          Material
          <input value={material} onChange={(e) => setMaterial(e.target.value)} required
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100" />
        </label>
        <div className="sm:col-span-3">
          <button type="submit" disabled={busy || designs.length === 0}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60">
            {busy ? "Creating…" : "Create part (seeds DESIGN_CREATED)"}
          </button>
          {designs.length === 0 ? (
            <p className="mt-2 text-xs text-amber-300">
              No registered designs yet. Register one on the Design Security page first.
            </p>
          ) : null}
        </div>
      </form>
    </Panel>
  );
}
