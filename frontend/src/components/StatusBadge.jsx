const TONES = {
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  warn: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  error: "bg-red-500/15 text-red-300 ring-red-500/30",
  neutral: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

export function toneForStatus(value) {
  if (value === "ok" || value === "healthy") return "ok";
  if (value === "not_configured" || value === "degraded") return "warn";
  if (value === "error" || value === "unhealthy") return "error";
  return "neutral";
}

export default function StatusBadge({ tone = "neutral", children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone] ?? TONES.neutral}`}
    >
      {children}
    </span>
  );
}
