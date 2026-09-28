import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";

export default function HistoryPanel({ resource }) {
  const items = resource.data?.items ?? [];
  return (
    <Panel title="Inspection history">
      <ErrorBanner error={resource.error} prefix="Could not load history" />
      {items.length === 0 && !resource.loading ? (
        <p className="text-sm text-slate-400">No inspections yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-3">#</th>
                <th className="py-1 pr-3">Time</th>
                <th className="py-1 pr-3">Class</th>
                <th className="py-1 pr-3">Confidence</th>
                <th className="py-1 pr-3">Severity</th>
                <th className="py-1 pr-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {items.map((row) => (
                <tr key={row.id}>
                  <td className="py-1.5 pr-3 text-slate-500">{row.id}</td>
                  <td className="py-1.5 pr-3 whitespace-nowrap">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="py-1.5 pr-3">{row.defect_type}</td>
                  <td className="py-1.5 pr-3">{(row.confidence * 100).toFixed(1)}%</td>
                  <td className="py-1.5 pr-3">{row.severity}</td>
                  <td className="py-1.5 pr-3">
                    <StatusBadge tone={row.status === "normal" ? "ok" : "error"}>{row.status}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
