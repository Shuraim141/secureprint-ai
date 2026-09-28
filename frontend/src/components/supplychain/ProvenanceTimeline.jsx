import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { WORKFLOW_STEPS } from "./workflow";
import { api } from "../../services/api";

export default function ProvenanceTimeline({ part, canAdvance, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [verification, setVerification] = useState(null);

  const done = new Set(part.events.map((e) => e.action));
  const nextIndex = part.events.length; // events are strictly in workflow order
  const nextStep = nextIndex < WORKFLOW_STEPS.length ? WORKFLOW_STEPS[nextIndex] : null;

  async function advance() {
    if (!nextStep) return;
    setBusy(true);
    setError(null);
    try {
      await api.addProvenanceEvent(part.part.id, { action: nextStep });
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      setVerification(await api.verifyPartChain(part.part.id));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title={`Provenance · ${part.part.part_code}`}
      action={
        <div className="flex gap-2">
          {canAdvance && nextStep ? (
            <button type="button" onClick={advance} disabled={busy}
              className="rounded-lg bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-60">
              {busy ? "Working…" : `Advance: ${nextStep}`}
            </button>
          ) : null}
          <button type="button" onClick={verify} disabled={busy}
            className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-60">
            Verify chain
          </button>
        </div>
      }
    >
      <ErrorBanner error={error} />
      {verification ? (
        <div role="status" className={`mb-3 rounded-lg px-4 py-2 text-sm ${verification.valid ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}`}>
          {verification.valid
            ? `Chain intact: ${verification.checked} events verified (hashes + Ed25519 signatures).`
            : `INTEGRITY FAILURE at event #${verification.first_broken_event}: ${verification.reason}`}
        </div>
      ) : null}
      <ol className="space-y-1">
        {WORKFLOW_STEPS.map((step, index) => {
          const eventRow = part.events.find((e) => e.action === step);
          const isDone = done.has(step);
          return (
            <li key={step} className="flex items-center gap-3 py-1.5 text-sm">
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${isDone ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-500"}`}>
                {index + 1}
              </span>
              <span className={isDone ? "text-slate-100" : "text-slate-500"}>{step}</span>
              {eventRow ? (
                <span className="ml-auto text-xs text-slate-500">
                  {eventRow.actor} · {new Date(eventRow.timestamp).toLocaleString()}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="mt-3 space-y-1">
        {part.events.map((eventRow) => (
          <details key={eventRow.event_id} className="text-xs text-slate-500">
            <summary className="cursor-pointer">{eventRow.event_id}</summary>
            <div className="ml-4 mt-1 space-y-0.5 font-mono">
              <div>hash: {eventRow.hash}</div>
              <div>prev_hash: {eventRow.prev_hash}</div>
              <div>signature: {eventRow.signature.slice(0, 32)}…</div>
            </div>
          </details>
        ))}
      </div>
    </Panel>
  );
}
