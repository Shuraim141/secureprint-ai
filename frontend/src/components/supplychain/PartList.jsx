import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";

export default function PartList({ resource, selectedId, onSelect }) {
  const parts = resource.data ?? [];
  return (
    <Panel title="Manufactured parts">
      <ErrorBanner error={resource.error} prefix="Could not load parts" />
      {parts.length === 0 && !resource.loading ? (
        <p className="text-sm text-slate-400">No parts yet.</p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {parts.map((part) => (
            <li key={part.id}>
              <button
                type="button"
                onClick={() => onSelect(part.id)}
                className={`flex w-full items-center justify-between gap-3 px-2 py-2 text-left text-sm hover:bg-slate-800/60 ${selectedId === part.id ? "bg-sky-500/10" : ""}`}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-100">{part.part_code}</span>
                  <span className="block text-xs text-slate-400">
                    {part.design_code} · {part.batch} · {part.material}
                  </span>
                </span>
                <StatusBadge tone="neutral">{part.status}</StatusBadge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
