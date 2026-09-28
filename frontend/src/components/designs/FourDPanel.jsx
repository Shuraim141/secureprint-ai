import { useState } from "react";

import ErrorBanner from "../ErrorBanner";
import Panel from "../Panel";
import StatusBadge from "../StatusBadge";
import { api } from "../../services/api";

const TRIGGERS = ["temperature", "humidity", "light", "magnetic_field", "electric_field", "ph", "time"];

const DEFAULTS = {
  material_id: "SMP-PLA-01",
  material_name: "Shape-memory PLA",
  material_class: "shape-memory polymer",
  trigger_type: "temperature",
  trigger_temperature_c: "60",
  trigger_time_s: "30",
  target_state: "folded",
  transformation_profile: '{"shape_recovery_ratio": 0.95}',
  activation_conditions: '{"min_hold_seconds": 30}',
};

function Row({ label, children }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right text-slate-200">{children}</dd>
    </div>
  );
}

export default function FourDPanel({ design, canEdit, onChanged }) {
  const profile = design.profile_4d;
  const [form, setForm] = useState(DEFAULTS);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [check, setCheck] = useState(null);

  const set = (key) => (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }));

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        material_id: form.material_id,
        material_name: form.material_name,
        material_class: form.material_class,
        trigger_type: form.trigger_type,
        trigger_temperature_c: form.trigger_temperature_c === "" ? null : Number(form.trigger_temperature_c),
        trigger_time_s: form.trigger_time_s === "" ? null : Number(form.trigger_time_s),
        target_state: form.target_state,
        transformation_profile: JSON.parse(form.transformation_profile || "{}"),
        activation_conditions: JSON.parse(form.activation_conditions || "{}"),
      };
      await api.save4dProfile(design.id, body);
      setEditing(false);
      setCheck(null);
      onChanged();
    } catch (caught) {
      setError(caught instanceof SyntaxError ? new Error("Profile fields must be valid JSON") : caught);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      setCheck(await api.verify4dProfile(design.id));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100";
  return (
    <Panel
      title="4D printing metadata"
      action={
        canEdit ? (
          <button
            type="button"
            onClick={() => setEditing((value) => !value)}
            className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800"
          >
            {editing ? "Cancel" : profile ? "Replace profile" : "Add 4D profile"}
          </button>
        ) : null
      }
    >
      <p className="mb-3 text-xs text-slate-500">
        A metadata and security representation of intended shape-change behaviour. It is not a physical 4D
        printer or material simulation.
      </p>
      <ErrorBanner error={error} />
      {profile ? (
        <>
          <dl className="divide-y divide-slate-800">
            <Row label="Material">{profile.material_name} ({profile.material_id})</Row>
            <Row label="Material class">{profile.material_class}</Row>
            <Row label="Trigger">{profile.trigger_type}</Row>
            <Row label="Trigger temperature">{profile.trigger_temperature_c ?? "—"} °C</Row>
            <Row label="Trigger time">{profile.trigger_time_s ?? "—"} s</Row>
            <Row label="Target state">{profile.target_state}</Row>
            <Row label="Bound to design version">v{profile.design_version}</Row>
            <Row label="Set by">{profile.created_by}</Row>
          </dl>
          <div className="mt-3 text-xs text-slate-400">
            Security fingerprint (SHA-256 of profile + design geometry)
            <div className="break-all font-mono text-slate-300" data-testid="fourd-fingerprint">
              {profile.security_fingerprint}
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={verify}
              disabled={busy}
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-60"
            >
              Verify 4D fingerprint
            </button>
            {check ? (
              <StatusBadge tone={check.intact ? "ok" : "error"}>
                {check.intact ? "INTACT" : "TAMPERED"}
              </StatusBadge>
            ) : null}
            {check ? <span className="text-xs text-slate-400">{check.reason}</span> : null}
          </div>
        </>
      ) : (
        <p className="text-sm text-slate-400">No 4D profile has been recorded for this design.</p>
      )}
      {editing ? (
        <form onSubmit={save} className="mt-4 grid gap-3 sm:grid-cols-2">
          {[
            ["material_id", "Material ID"],
            ["material_name", "Material name"],
            ["material_class", "Material class"],
            ["target_state", "Target state"],
            ["trigger_temperature_c", "Trigger temperature (°C)"],
            ["trigger_time_s", "Trigger time (s)"],
          ].map(([key, label]) => (
            <label key={key} className="text-xs text-slate-300">
              {label}
              <input value={form[key]} onChange={set(key)} className={input} />
            </label>
          ))}
          <label className="text-xs text-slate-300">
            Trigger type
            <select value={form.trigger_type} onChange={set("trigger_type")} className={input}>
              {TRIGGERS.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <span />
          <label className="text-xs text-slate-300">
            Transformation profile (JSON)
            <textarea rows={3} value={form.transformation_profile} onChange={set("transformation_profile")} className={`${input} font-mono`} />
          </label>
          <label className="text-xs text-slate-300">
            Activation conditions (JSON)
            <textarea rows={3} value={form.activation_conditions} onChange={set("activation_conditions")} className={`${input} font-mono`} />
          </label>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
            >
              Save 4D profile
            </button>
          </div>
        </form>
      ) : null}
    </Panel>
  );
}
