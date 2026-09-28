import { useRef, useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { api } from "../../services/api";
import { saveBlob } from "../../services/download";
import { formatBytes, formatNumber } from "../../utils/format";
import FourDPanel from "./FourDPanel";

function Stat({ label, value, tone = null }) {
  return (
    <div className="rounded-lg border border-slate-800 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-lg font-semibold ${tone === "bad" ? "text-red-300" : "text-slate-100"}`}>{value}</div>
    </div>
  );
}

function Hash({ label, value, note }) {
  return (
    <div className="py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="break-all font-mono text-xs text-slate-200">{value}</div>
      {note ? <div className="text-[11px] text-slate-500">{note}</div> : null}
    </div>
  );
}

export default function DesignDetail({ design, canManage, canDownload, onChanged }) {
  const versionRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const current = design.versions[design.versions.length - 1];
  const analysis = current.analysis;
  const fingerprints = Object.fromEntries(current.fingerprints.map((f) => [f.kind, f]));
  const watermark = fingerprints.watermark?.meta;

  async function download(kind, version) {
    setError(null);
    try {
      const { blob, filename } =
        kind === "watermarked"
          ? await api.downloadWatermarked(design.id, version)
          : await api.downloadVersion(design.id, version);
      saveBlob(blob, filename);
    } catch (caught) {
      setError(caught);
    }
  }

  async function addVersion(event) {
    event.preventDefault();
    const file = versionRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.addDesignVersion(design.id, file);
      versionRef.current.value = "";
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Panel
        title={`${design.design_code} · ${design.name}`}
        action={
          <div className="flex gap-1">
            <StatusBadge tone={current.encrypted ? "ok" : "error"}>
              {current.encrypted ? `encrypted · ${current.encryption_alg}` : "NOT encrypted"}
            </StatusBadge>
            <StatusBadge tone="neutral">v{design.current_version}</StatusBadge>
          </div>
        }
      >
        <ErrorBanner error={error} />
        <dl className="grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <div className="flex justify-between"><dt className="text-slate-400">Owner</dt><dd>{design.owner}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">Format</dt><dd>{design.file_format.toUpperCase()}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">Registered</dt><dd>{new Date(design.created_at).toLocaleString()}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">File size</dt><dd>{formatBytes(current.file_size)}</dd></div>
        </dl>

        <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">
          3D model analysis (computed from the vertices, current version)
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Triangles" value={formatNumber(analysis.triangle_count, 0)} />
          <Stat label="Vertices" value={formatNumber(analysis.vertex_count, 0)} />
          <Stat label="Size X (mm)" value={formatNumber(analysis.dimensions_mm.x)} />
          <Stat label="Size Y (mm)" value={formatNumber(analysis.dimensions_mm.y)} />
          <Stat label="Size Z (mm)" value={formatNumber(analysis.dimensions_mm.z)} />
          <Stat
            label={analysis.volume_reliable ? "Volume (mm³)" : "Volume (mm³, unreliable)"}
            value={formatNumber(analysis.volume_mm3)}
          />
          <Stat label="Surface area (mm²)" value={formatNumber(analysis.surface_area_mm2)} />
          <Stat
            label="Watertight"
            value={analysis.watertight ? "yes" : "NO"}
            tone={analysis.watertight ? null : "bad"}
          />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Bounding box min {analysis.bounding_box_min.join(", ")} · max {analysis.bounding_box_max.join(", ")}.
          Units assumed: {analysis.units_assumed}.
        </p>
        {analysis.warnings.length > 0 ? (
          <ul className="mt-2 list-inside list-disc text-sm text-amber-300">
            {analysis.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-emerald-300">Geometry checks passed: closed, consistent mesh.</p>
        )}

        <h3 className="mb-1 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Fingerprints</h3>
        <div className="divide-y divide-slate-800">
          <Hash label="SHA-256 (exact file bytes)" value={current.sha256} note="Any single changed byte changes this hash." />
          <Hash
            label="Geometric fingerprint (canonical shape, SPGF1)"
            value={fingerprints.geometric?.value}
            note="Same shape in another format or triangle order gives the same value. Not a watermark."
          />
        </div>

        <h3 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Watermark (fragile prototype, separate from the fingerprints)
        </h3>
        {watermark?.status === "applied" ? (
          <div className="text-sm text-slate-300">
            <StatusBadge tone="ok">applied</StatusBadge>{" "}
            <span className="text-slate-400">
              64-bit owner tag {watermark.tag_hex} in {watermark.samples} coordinates; largest coordinate
              change {watermark.max_abs_change.toExponential(2)} mm.
            </span>
            <p className="mt-1 text-xs text-slate-500">{watermark.note}</p>
          </div>
        ) : (
          <div className="text-sm text-slate-400">
            <StatusBadge tone="warn">not applied</StatusBadge> {watermark?.reason}
          </div>
        )}

        <h3 className="mb-1 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Versions</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-3">Ver</th>
                <th className="py-1 pr-3">File</th>
                <th className="py-1 pr-3">Size</th>
                <th className="py-1 pr-3">By</th>
                <th className="py-1 pr-3">SHA-256</th>
                {canDownload ? <th className="py-1">Download</th> : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {design.versions.map((version) => (
                <tr key={version.version}>
                  <td className="py-1.5 pr-3">v{version.version}</td>
                  <td className="py-1.5 pr-3">{version.original_filename}</td>
                  <td className="py-1.5 pr-3">{formatBytes(version.file_size)}</td>
                  <td className="py-1.5 pr-3">{version.created_by}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{version.sha256.slice(0, 16)}…</td>
                  {canDownload ? (
                    <td className="py-1.5">
                      <button type="button" onClick={() => download("original", version.version)}
                        className="mr-2 text-sky-400 underline">
                        original (decrypt)
                      </button>
                      <button type="button" onClick={() => download("watermarked", version.version)}
                        className="text-sky-400 underline">
                        watermarked copy
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canManage ? (
          <form onSubmit={addVersion} className="mt-3 flex flex-wrap items-center gap-3">
            <input ref={versionRef} type="file" accept=".stl,.obj,.3mf" required
              className="text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-200" />
            <button type="submit" disabled={busy}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60">
              {busy ? "Uploading…" : "Upload new version"}
            </button>
          </form>
        ) : null}
      </Panel>

      <Panel title="Design history (provenance)">
        <ol className="space-y-2 border-l border-slate-700 pl-4">
          {design.history.map((event, index) => (
            <li key={`${event.event}-${index}`} className="text-sm">
              <div className="text-slate-100">{event.event.replaceAll("_", " ")}</div>
              <div className="text-xs text-slate-400">
                {new Date(event.time).toLocaleString()} · {event.actor} · {event.detail}
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-slate-500">
          Built from the recorded versions and profile. The tamper-evident signed hash chain for parts
          and manufacturing events arrives with the supply-chain module (Phase 6).
        </p>
      </Panel>

      <FourDPanel design={design} canEdit={canManage} onChanged={onChanged} />
    </div>
  );
}
