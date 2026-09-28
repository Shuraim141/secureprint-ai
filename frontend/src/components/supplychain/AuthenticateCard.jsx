import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { api } from "../../services/api";

const TONE = { AUTHENTIC: "ok", TAMPERED: "error", INVALID: "error", UNKNOWN: "warn" };

export default function AuthenticateCard({ initialCode = "" }) {
  const [code, setCode] = useState(initialCode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.authenticatePart(code.trim()));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Authenticate a part">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <ErrorBanner error={error} />
        <label className="text-xs text-slate-300">
          Part ID / code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="PART-000001"
            className="mt-1 w-48 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
          />
        </label>
        <button type="submit" disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60">
          {busy ? "Checking…" : "Authenticate"}
        </button>
      </form>
      {result ? (
        <div className="mt-4 space-y-2 border-t border-slate-800 pt-4" data-testid="authenticate-result">
          <StatusBadge tone={TONE[result.verdict] ?? "neutral"}>{result.verdict}</StatusBadge>
          <p className="text-sm text-slate-300">{result.reason}</p>
          {result.chain_verification ? (
            <p className="text-xs text-slate-500">
              Chain: {result.chain_verification.checked} event(s) checked
              {result.chain_verification.first_broken_event
                ? `, broken at event #${result.chain_verification.first_broken_event}`
                : ", all valid"}
              .
            </p>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}
