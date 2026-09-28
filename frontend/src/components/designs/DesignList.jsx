import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { shortHash } from "../../utils/format";

export default function DesignList({ resource, selectedId, onSelect }) {
  const designs = resource.data ?? [];
  return (
    <Panel title="Registered designs">
      <ErrorBanner error={resource.error} prefix="Could not load designs" />
      {designs.length === 0 && !resource.loading ? (
        <p className="text-sm text-slate-400">No designs yet. Register one to see its analysis here.</p>
      ) : null}
      <ul className="divide-y divide-slate-800">
        {designs.map((design) => (
          <li key={design.id}>
            <button
              type="button"
              onClick={() => onSelect(design.id)}
              className={`flex w-full items-center justify-between gap-3 px-2 py-2 text-left text-sm hover:bg-slate-800/60 ${selectedId === design.id ? "bg-sky-500/10" : ""}`}
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-slate-100">{design.name}</span>
                <span className="block text-xs text-slate-400">
                  {design.design_code} · v{design.current_version} · {design.file_format.toUpperCase()} ·{" "}
                  {design.triangle_count ?? "?"} triangles · owner {design.owner}
                </span>
                <span className="block font-mono text-[11px] text-slate-500">{shortHash(design.sha256)}</span>
              </span>
              <span className="flex shrink-0 gap-1">
                {design.encrypted ? <StatusBadge tone="ok">encrypted</StatusBadge> : null}
                {design.is_4d ? <StatusBadge tone="neutral">4D</StatusBadge> : null}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
