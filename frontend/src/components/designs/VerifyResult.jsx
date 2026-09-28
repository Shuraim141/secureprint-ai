import StatusBadge from "../StatusBadge";
import { formatNumber, shortHash } from "../../utils/format";

const TONES = {
  AUTHENTIC: "ok",
  GEOMETRY_MATCH: "warn",
  UNREGISTERED: "warn",
  TAMPERED: "error",
  INVALID_FILE: "error",
  WRONG_DESIGN: "error",
};

const LABELS = {
  triangle_count: "Triangles",
  vertex_count: "Vertices",
  volume_mm3: "Volume (mm³)",
  surface_area_mm2: "Surface area (mm²)",
  dimension_x_mm: "Size X (mm)",
  dimension_y_mm: "Size Y (mm)",
  dimension_z_mm: "Size Z (mm)",
};

function Check({ label, ok, detail }) {
  return (
    <li className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-slate-300">{label}</span>
      <StatusBadge tone={ok ? "ok" : "neutral"}>{detail ?? (ok ? "match" : "no match")}</StatusBadge>
    </li>
  );
}

export default function VerifyResult({ result }) {
  const tone = TONES[result.verdict] ?? "neutral";
  const watermark = result.checks?.watermark;
  const metrics = result.differences?.metrics ?? null;
  return (
    <div className="space-y-3" data-testid="verify-result">
      <div className="flex flex-wrap items-center gap-3">
        <span data-testid="verdict">
          <StatusBadge tone={tone}>{result.verdict}</StatusBadge>
        </span>
        <span className="text-sm text-slate-200">{result.headline}</span>
      </div>
      <ul className="list-inside list-disc text-sm text-slate-400">
        {result.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <ul className="divide-y divide-slate-800 rounded-lg border border-slate-800 px-3">
        <Check label="SHA-256 (exact bytes)" ok={result.checks.sha256_match} />
        <Check label="Geometric fingerprint (shape)" ok={result.checks.geometric_match} />
        <Check
          label="Keyed watermark"
          ok={Boolean(watermark?.detected)}
          detail={
            watermark
              ? watermark.detected
                ? `found (score ${watermark.score})`
                : watermark.score !== undefined
                  ? `not found (score ${watermark.score})`
                  : "not applicable"
              : "not checked"
          }
        />
      </ul>
      <div className="font-mono text-xs text-slate-500">
        Uploaded SHA-256: <span className="break-all">{result.sha256}</span>
      </div>
      {result.matched_design ? (
        <div className="text-sm text-slate-300">
          Related registered design: <strong>{result.matched_design.design_code}</strong> ·{" "}
          {result.matched_design.name} · v{result.matched_design.version}
        </div>
      ) : null}
      {metrics ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="differences">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-4">Metric</th>
                <th className="py-1 pr-4">Registered</th>
                <th className="py-1 pr-4">Uploaded</th>
                <th className="py-1 pr-4">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {Object.entries(metrics).map(([key, m]) => (
                <tr key={key} className={m.changed ? "text-red-300" : "text-slate-400"}>
                  <td className="py-1 pr-4">{LABELS[key] ?? key}</td>
                  <td className="py-1 pr-4">{formatNumber(m.registered)}</td>
                  <td className="py-1 pr-4">{formatNumber(m.uploaded)}</td>
                  <td className="py-1 pr-4">
                    {m.changed ? `${m.delta > 0 ? "+" : ""}${formatNumber(m.delta)}` : "unchanged"}
                    {m.changed && m.delta_pct !== null ? ` (${formatNumber(m.delta_pct, 2)}%)` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : result.uploaded_geometric_fingerprint ? (
        <div className="font-mono text-xs text-slate-500">
          Uploaded geometric fingerprint: {shortHash(result.uploaded_geometric_fingerprint, 24)}
        </div>
      ) : null}
    </div>
  );
}
