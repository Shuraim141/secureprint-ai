/** Lightweight inline SVG line chart: nozzle temperature and speed over the recent ticks.
 * No charting library needed for a handful of points polled once per second. */
export default function TelemetryChart({ samples }) {
  if (samples.length < 2) return null;
  const width = 560;
  const height = 120;
  const pad = 8;

  function toPoints(values, max) {
    const step = (width - pad * 2) / (values.length - 1);
    return values
      .map((v, i) => `${pad + i * step},${height - pad - (v / max) * (height - pad * 2)}`)
      .join(" ");
  }

  const temps = samples.map((s) => s.temperature);
  const speeds = samples.map((s) => s.speed);
  const tempMax = Math.max(260, ...temps);
  const speedMax = Math.max(100, ...speeds);
  const anomalyIndex = samples.findIndex((s) => s.anomaly);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full rounded-lg border border-slate-800 bg-slate-950">
      <polyline points={toPoints(temps, tempMax)} fill="none" stroke="#f97316" strokeWidth="1.5" />
      <polyline points={toPoints(speeds, speedMax)} fill="none" stroke="#38bdf8" strokeWidth="1.5" />
      {anomalyIndex >= 0 ? (
        <line
          x1={pad + anomalyIndex * ((width - pad * 2) / (samples.length - 1))}
          x2={pad + anomalyIndex * ((width - pad * 2) / (samples.length - 1))}
          y1={pad} y2={height - pad} stroke="#ef4444" strokeWidth="1" strokeDasharray="3,3"
        />
      ) : null}
      <text x={pad} y={14} fill="#f97316" fontSize="10">nozzle °C</text>
      <text x={pad + 70} y={14} fill="#38bdf8" fontSize="10">speed mm/s</text>
    </svg>
  );
}
