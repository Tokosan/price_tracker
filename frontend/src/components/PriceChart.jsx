import { useMemo, useState } from "react";
import { formatDate, formatPrice } from "../format.js";

// Gráfico escalonado del historial (un precio vale hasta la lectura siguiente).
// SVG a mano: sin dependencias y liviano.
export default function PriceChart({ points, currency }) {
  const [hover, setHover] = useState(null);
  const W = 640, H = 220, PL = 64, PR = 12, PT = 12, PB = 28;

  const data = useMemo(
    () => points.filter((p) => p.price !== null).map((p) => ({ ...p, t: new Date(p.checked_at).getTime() })),
    [points],
  );
  if (data.length === 0) return <p className="muted">Aún no hay lecturas con precio.</p>;

  const now = Date.now();
  const t0 = data[0].t;
  const t1 = Math.max(now, data[data.length - 1].t + 1);
  let lo = Math.min(...data.map((d) => d.price));
  let hi = Math.max(...data.map((d) => d.price));
  if (lo === hi) {
    lo = Math.floor(lo * 0.9);
    hi = Math.ceil(hi * 1.1) || 1;
  }
  const pad = (hi - lo) * 0.1;
  lo = Math.max(0, lo - pad);
  hi += pad;
  const x = (t) => PL + ((t - t0) / (t1 - t0 || 1)) * (W - PL - PR);
  const y = (v) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB);

  let d = "";
  data.forEach((p, i) => {
    const px = x(p.t), py = y(p.price);
    d += i === 0 ? `M${px},${py}` : ` H${px} V${py}`;
  });
  d += ` H${x(t1)}`;

  const ticks = [lo, (lo + hi) / 2, hi];
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = t0 + (((e.clientX - rect.left) / rect.width) * W - PL) / (W - PL - PR) * (t1 - t0);
    let best = data[0];
    for (const p of data) if (p.t <= t) best = p;
    setHover(best);
  };

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label="Historial de precios">
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={PL} x2={W - PR} y1={y(v)} y2={y(v)} className="grid" />
            <text x={PL - 6} y={y(v) + 4} textAnchor="end" className="axis">{formatPrice(Math.round(v), currency)}</text>
          </g>
        ))}
        <text x={PL} y={H - 8} className="axis">{formatDate(new Date(t0).toISOString())}</text>
        <text x={W - PR} y={H - 8} textAnchor="end" className="axis">hoy</text>
        <path d={d} className="line" />
        {data.map((p, i) => (
          <circle key={i} cx={x(p.t)} cy={y(p.price)} r={p === hover ? 4.5 : 2.5} className={p.available ? "dot" : "dot out"} />
        ))}
      </svg>
      <div className="chart-info">
        {hover ? (
          <>
            <b>{formatPrice(hover.price, currency)}</b> · {formatDate(hover.checked_at)}
            {!hover.available && " · sin stock"}
          </>
        ) : (
          <span className="muted">{data.length} lecturas · pasa el cursor para ver el detalle</span>
        )}
      </div>
    </div>
  );
}
