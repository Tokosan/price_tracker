import { useMemo, useState } from "react";
import { formatDate, formatPrice } from "../format.js";

// Valor de una serie escalonada en el instante t: la última lectura en o antes de t.
function valueAt(data, t) {
  let best = null;
  for (const p of data) {
    if (p.t > t) break;
    best = p;
  }
  return best;
}

// Gráfico escalonado del historial (un precio vale hasta la lectura siguiente), con una
// línea por link y, si hay varios, la del mejor precio con stock del grupo por detrás.
// SVG a mano: sin dependencias y liviano. `series`: [{key, label, color, points}].
export default function PriceChart({ series, currency }) {
  const [hover, setHover] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());
  const W = 640, H = 220, PL = 64, PR = 12, PT = 12, PB = 28;
  const multi = series.length > 1;

  const all = useMemo(
    () =>
      series.map((s) => ({
        ...s,
        data: s.points.filter((p) => p.price !== null).map((p) => ({ ...p, t: new Date(p.checked_at).getTime() })),
      })),
    [series],
  );
  const shown = all.filter((s) => !hidden.has(s.key) && s.data.length > 0);
  const times = useMemo(() => [...new Set(all.flatMap((s) => s.data.map((p) => p.t)))].sort((a, b) => a - b), [all]);

  // Mínimo con stock entre las series visibles, en cada instante con lecturas.
  const minLine = useMemo(() => {
    if (!multi) return [];
    const out = [];
    for (const t of times) {
      let best = null;
      for (const s of shown) {
        const p = valueAt(s.data, t);
        if (p && p.available && (best === null || p.price < best)) best = p.price;
      }
      if (out.length === 0 || out[out.length - 1].price !== best) out.push({ t, price: best });
    }
    return out;
  }, [multi, times, shown]);

  if (shown.length === 0 && all.every((s) => s.data.length === 0))
    return <p className="muted">Aún no hay lecturas con precio.</p>;

  const now = Date.now();
  const visible = shown.flatMap((s) => s.data);
  const t0 = visible.length ? Math.min(...visible.map((d) => d.t)) : now - 1;
  const t1 = Math.max(now, ...visible.map((d) => d.t + 1));
  let lo = visible.length ? Math.min(...visible.map((d) => d.price)) : 0;
  let hi = visible.length ? Math.max(...visible.map((d) => d.price)) : 1;
  if (lo === hi) {
    lo = Math.floor(lo * 0.9);
    hi = Math.ceil(hi * 1.1) || 1;
  }
  const pad = (hi - lo) * 0.1;
  lo = Math.max(0, lo - pad);
  hi += pad;
  const x = (t) => PL + ((t - t0) / (t1 - t0 || 1)) * (W - PL - PR);
  const y = (v) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB);

  const stepPath = (data) => {
    let d = "";
    let open = false;
    data.forEach((p) => {
      const px = x(p.t);
      if (p.price === null) {
        if (open) d += ` H${px}`;
        open = false;
        return;
      }
      const py = y(p.price);
      d += open ? ` H${px} V${py}` : ` M${px},${py}`;
      open = true;
    });
    if (open) d += ` H${x(t1)}`;
    return d.trim();
  };

  const ticks = [lo, (lo + hi) / 2, hi];
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((((e.clientX - rect.left) / rect.width) * W - PL) / (W - PL - PR)) * (t1 - t0);
    setHover(Math.max(t0, Math.min(t, t1)));
  };
  const toggle = (key) => {
    const next = new Set(hidden);
    next.has(key) ? next.delete(key) : next.add(key);
    setHidden(next);
  };

  // Lo que se ve bajo el cursor: el valor de cada serie en ese instante.
  const rows =
    hover === null
      ? []
      : shown
          .map((s) => ({ s, p: valueAt(s.data, hover) }))
          .filter((r) => r.p)
          .sort((a, b) => a.p.price - b.p.price);
  const minAtHover = hover === null ? null : valueAt(minLine, hover);

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
        {multi && minLine.length > 0 && <path d={stepPath(minLine)} className="line min" />}
        {shown.map((s) => (
          <g key={s.key} style={{ "--series": s.color }}>
            <path d={stepPath(s.data)} className="line" />
            {s.data.map((p, i) => (
              <circle key={i} cx={x(p.t)} cy={y(p.price)} r={2.5} className={p.available ? "dot" : "dot out"} />
            ))}
          </g>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PT} y2={H - PB} className="crosshair" />}
        {rows.map(({ s, p }) => (
          <circle key={s.key} cx={x(hover)} cy={y(p.price)} r={4.5} className="dot hover" style={{ "--series": s.color }} />
        ))}
      </svg>
      {multi && (
        <div className="legend">
          {all.map((s) => (
            <button
              key={s.key}
              type="button"
              className={"legend-item" + (hidden.has(s.key) ? " off" : "")}
              aria-pressed={!hidden.has(s.key)}
              onClick={() => toggle(s.key)}
              title={hidden.has(s.key) ? "Mostrar" : "Ocultar"}
            >
              <span className="swatch" style={{ "--series": s.color }} />
              {s.label}
            </button>
          ))}
          <span className="legend-item static">
            <span className="swatch min" />
            Mejor precio con stock
          </span>
        </div>
      )}
      <div className="chart-info">
        {hover === null ? (
          <span className="muted">
            {visible.length} lecturas · pasa el cursor para ver el detalle
          </span>
        ) : multi ? (
          <>
            <span className="muted">{formatDate(new Date(hover).toISOString())}</span>
            {minAtHover?.price != null && <> · mejor <b>{formatPrice(minAtHover.price, currency)}</b></>}
            <ul className="chart-rows">
              {rows.map(({ s, p }) => (
                <li key={s.key}>
                  <span className="swatch" style={{ "--series": s.color }} />
                  {s.label}: <b>{formatPrice(p.price, currency)}</b>
                  {!p.available && " · sin stock"}
                </li>
              ))}
            </ul>
          </>
        ) : rows[0] ? (
          <>
            <b>{formatPrice(rows[0].p.price, currency)}</b> · {formatDate(rows[0].p.checked_at)}
            {!rows[0].p.available && " · sin stock"}
          </>
        ) : (
          <span className="muted">Sin lecturas antes de esa fecha.</span>
        )}
      </div>
    </div>
  );
}
