import { useRef, useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import { api } from "../../services/api";
import VerifyResult from "./VerifyResult";

export default function VerifyCard({ selectedDesign, onVerified }) {
  const fileRef = useRef(null);
  const [useSelected, setUseSelected] = useState(true);
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
      const outcome = await api.verifyDesign(file, selectedDesign && useSelected ? selectedDesign.id : null);
      setResult(outcome);
      onVerified?.(outcome);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Verify a file against the registry">
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorBanner error={error} prefix="Verification failed" />
        <label className="block text-sm text-slate-300">
          File to check
          <input
            ref={fileRef}
            type="file"
            accept=".stl,.obj,.3mf"
            required
            className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-200"
          />
        </label>
        {selectedDesign ? (
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={useSelected} onChange={(e) => setUseSelected(e.target.checked)} />
            Compare against the selected design ({selectedDesign.design_code})
          </label>
        ) : (
          <p className="text-xs text-slate-500">No design selected: the file is checked against the whole registry.</p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
        >
          {busy ? "Verifying…" : "Verify"}
        </button>
      </form>
      {result ? (
        <div className="mt-4 border-t border-slate-800 pt-4">
          <VerifyResult result={result} />
        </div>
      ) : null}
    </Panel>
  );
}
