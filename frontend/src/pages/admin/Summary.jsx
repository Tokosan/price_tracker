import { Link } from "react-router-dom";
import { PROCESSOR_LABEL } from "../../format.js";
import { useAdminData } from "./useAdmin.js";

const METRICS = [
  ["active_users", "Usuarios activos", (m) => `de ${m.users}`],
  ["watches", "Productos seguidos", (m) => `${m.active_watches} activos`],
  ["products", "Productos distintos"],
  ["price_points_24h", "Lecturas (24 h)"],
  ["notifications_7d", "Avisos (7 d)"],
  ["anomalies_7d", "Anomalías (7 d)"],
];

// Barras horizontales simples (CSS), sin librería.
function Bars({ rows, to }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="bars">
      {rows.map((r) => (
        <li key={r.key}>
          {to ? <Link to={to(r)}>{r.label}</Link> : <span>{r.label}</span>}
          <div className="bar"><div style={{ width: `${(r.value / max) * 100}%` }} /></div>
          <b>{r.value}</b>
        </li>
      ))}
    </ul>
  );
}

export default function Summary() {
  const { data, error } = useAdminData(["/api/admin/metrics", "/api/admin/users", "/api/admin/meli"]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Cargando…</p>;
  const [m, users, meli] = data;

  const attention = [
    m.broken_products > 0 && { text: `${m.broken_products} producto(s) broken`, to: "/admin/tiendas" },
    m.failing_products > m.broken_products && { text: `${m.failing_products - m.broken_products} producto(s) con fallos recientes`, to: "/admin/tiendas" },
    meli.configured && !meli.connected && { text: "MercadoLibre no está conectado", to: "/admin/tiendas" },
    users.some((u) => u.pending_invite_expires_at) && { text: "Hay invitaciones sin usar", to: "/admin/usuarios" },
  ].filter(Boolean);

  const byStore = Object.entries(m.products_by_processor)
    .map(([k, v]) => ({ key: k, label: PROCESSOR_LABEL[k] ?? k, value: v }))
    .sort((a, b) => b.value - a.value);
  const byUser = users
    .map((u) => ({ key: u.id, label: u.username, value: u.watch_count }))
    .sort((a, b) => b.value - a.value);

  return (
    <>
      <h1>Resumen</h1>
      <section className="metrics">
        {METRICS.map(([k, label, sub]) => (
          <div key={k} className="metric card">
            <div className="metric-value">{m[k]}</div>
            <div className="muted small">{label}{sub && <> · {sub(m)}</>}</div>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Requiere atención</h2>
        {attention.length === 0 ? (
          <p className="muted">Todo en orden.</p>
        ) : (
          <ul className="attention">
            {attention.map((a) => <li key={a.text}><Link to={a.to}>{a.text}</Link></li>)}
          </ul>
        )}
      </section>

      <div className="two-cols">
        <section className="card">
          <h2>Productos por tienda</h2>
          {byStore.length ? <Bars rows={byStore} /> : <p className="muted">Sin productos.</p>}
        </section>
        <section className="card">
          <h2>Productos por usuario</h2>
          <Bars rows={byUser} to={(r) => `/admin/productos?usuario=${r.key}`} />
        </section>
      </div>
    </>
  );
}
