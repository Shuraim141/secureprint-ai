import { useRef, useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import { api } from "../../services/api";

export default function UploadCard({ onRegistered }) {
  const fileRef = useRef(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [warnings, setWarnings] = useState([]);

  async function handleSubmit(event) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const design = await api.registerDesign(file, name.trim());
      setWarnings(design.warnings ?? []);
      setName("");
      fileRef.current.value = "";
      onRegistered(design);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Register a 3D design">
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorBanner error={error} prefix="Upload rejected" />
        <label className="block text-sm text-slate-300">
          Model file (.stl, .obj, .3mf)
          <input
            ref={fileRef}
            type="file"
            accept=".stl,.obj,.3mf"
            required
            className="mt-1 block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-200"
          />
        </label>
        <label className="block text-sm text-slate-300">
          Design name (optional)
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
        >
          {busy ? "Analysing, fingerprinting, encrypting…" : "Register design"}
        </button>
        {warnings.map((text) => (
          <div key={text} role="status" className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
            {text}
          </div>
        ))}
      </form>
    </Panel>
  );
}
