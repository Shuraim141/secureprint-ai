export default function StatCard({ label, value, hint = "", loading = false }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-2 text-3xl font-semibold text-slate-100" data-testid={`stat-${label}`}>
        {loading ? "…" : value}
      </div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}
