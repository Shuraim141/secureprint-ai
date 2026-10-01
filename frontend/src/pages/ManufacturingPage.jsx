import { useState } from "react";

import GCodeCard from "../components/manufacturing/GCodeCard";
import IncidentsPanel from "../components/manufacturing/IncidentsPanel";
import PrinterCard from "../components/manufacturing/PrinterCard";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";

export default function ManufacturingPage() {
  const { can } = useAuth();
  const canControl = can("printer:control");
  const canAnalyzeGcode = can("gcode:analyze");
  const canViewIncidents = can("incident:view");
  const [nonce, setNonce] = useState(0);

  // Each PrinterCard owns its own telemetry polling internally (see PrinterCard.jsx) -- this
  // list itself only needs the printer rows, not a parallel array of telemetry hooks, which
  // would call useResource a variable number of times and break React's Rules of Hooks.
  const printers = useResource((signal) => api.listPrinters(signal), {
    intervalMs: 1000, deps: [nonce],
  });
  const incidents = useResource((signal) => api.listIncidents({ limit: 10 }, signal), {
    enabled: canViewIncidents, intervalMs: 2000, deps: [nonce],
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Manufacturing Security</h1>
        <p className="text-sm text-slate-400">
          A local printer simulator (no physical hardware required) feeds live telemetry through
          hybrid anomaly detection: hard safety thresholds first, then an Isolation Forest for
          subtler statistical anomalies. A detected anomaly automatically pauses the print,
          opens an incident, and writes an audit record.
        </p>
      </div>

      <ErrorBanner error={printers.error} prefix="Could not load printers" />
      <div className="grid gap-6 lg:grid-cols-2">
        {(printers.data ?? []).map((printer) => (
          <PrinterCard
            key={printer.id}
            printer={printer}
            canControl={canControl}
            onChanged={() => setNonce((n) => n + 1)}
          />
        ))}
      </div>

      {canAnalyzeGcode ? <GCodeCard /> : null}
      {canViewIncidents ? <IncidentsPanel resource={incidents} /> : null}
    </div>
  );
}
