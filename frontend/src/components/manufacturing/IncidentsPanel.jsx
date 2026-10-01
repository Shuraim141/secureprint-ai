import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";

const TONE = { HIGH: "error", MEDIUM: "warn", LOW: "warn" };

export default function IncidentsPanel({ resource }) {
  const items = resource.data?.items ?? [];
  return (
    <Panel title="Security incidents">
      <ErrorBanner error={resource.error} prefix="Could not load incidents" />
      {items.length === 0 && !resource.loading ? (
        <p className="text-sm text-slate-400">No incidents recorded.</p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {items.map((incident) => (
            <li key={incident.id} className="py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-100">{incident.incident_code}</span>
                <StatusBadge tone={TONE[incident.severity] ?? "neutral"}>{incident.severity}</StatusBadge>
                <StatusBadge tone="neutral">{incident.status}</StatusBadge>
                <span className="text-xs text-slate-500">{new Date(incident.opened_at).toLocaleString()}</span>
              </div>
              <div className="mt-1 text-slate-300">{incident.description}</div>
              <div className="text-xs text-slate-500">Response: {incident.action_taken}</div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
