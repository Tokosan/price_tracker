import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { formatDate, formatPrice, PROCESSOR_LABEL, relative } from "../../format.js";
import { useAdminData } from "./useAdmin.js";

// Resumen corto de una regla para la tabla ("Baja 10 %", "Objetivo $49.990").
function ruleText(r, currency) {
  const p = r.params || {};
  switch (r.kind) {
    case "TARGET_PRICE": return `Objetivo ${formatPrice(p.value, currency)}`;
    case "DISCOUNT_PCT": return `Descuento ${p.pct} %`;
    case "PRICE_DROP": return `Baja ${p.min_pct} %`;
    case "PRICE_UP": return `Sube ${p.min_pct} %`;
    case "PRICE_CHANGE": return "Cambia";
    case "OUT_OF_STOCK": return "Se agota";
    case "BACK_IN_STOCK": return "Vuelve el stock";
    default: return r.kind;
  }
}

function Change({ from, to }) {
  if (from == null || to == null || !from) return <span className="muted">—</span>;
  const pct = ((to - from) / from) * 100;
  if (Math.abs(pct) < 0.5) return <span className="muted">=</span>;
  return <span className={pct < 0 ? "down" : "up"}>{pct < 0 ? "▼" : "▲"} {Math.abs(pct).toFixed(0)} %</span>;
}

function StockBadge({ product }) {
  if (product.status === "broken") return <span className="badge out">Broken</span>;
  if (product.available === false) return <span className="badge out">Sin stock</span>;
  return null;
}

export default function Products() {
  const [params, setParams] = useSearchParams();
  const userId = params.get("usuario");
  const { data, error } = useAdminData(["/api/admin/users", "/api/admin/products?status=all"]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Cargando…</p>;
  const [users, products] = data;
  const select = (id) => setParams(id ? { usuario: id } : {});

  return (
    <>
      <h1>Productos</h1>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={!userId} className={!userId ? "on" : ""} onClick={() => select(null)}>
          Todos <span className="count">{products.length}</span>
        </button>
        {users.map((u) => (
          <button key={u.id} role="tab" aria-selected={userId === String(u.id)} className={userId === String(u.id) ? "on" : ""} onClick={() => select(u.id)}>
            {u.username} <span className="count">{u.watch_count}</span>
          </button>
        ))}
      </div>
      {userId ? (
        <UserWatches key={userId} user={users.find((u) => String(u.id) === userId)} userId={userId} />
      ) : (
        <AllProducts products={products} onUser={(name) => select(users.find((u) => u.username === name)?.id)} />
      )}
    </>
  );
}

function AllProducts({ products, onUser }) {
  const [q, setQ] = useState("");
  const [store, setStore] = useState("");
  const stores = [...new Set(products.map((p) => p.processor))].sort();
  const shown = useMemo(() => {
    const text = q.trim().toLocaleLowerCase("es");
    return products
      .filter((p) => (!store || p.processor === store) && (!text || p.title.toLocaleLowerCase("es").includes(text)))
      .sort((a, b) => b.watchers - a.watchers || a.title.localeCompare(b.title, "es"));
  }, [products, q, store]);

  const followed = products.filter((p) => p.watchers > 0);
  const shared = followed.filter((p) => p.watchers > 1).length;
  return (
    <>
      <section className="metrics">
        <div className="metric card"><div className="metric-value">{followed.length}</div><div className="muted small">Productos con seguidores</div></div>
        <div className="metric card"><div className="metric-value">{shared}</div><div className="muted small">Seguidos por 2 o más</div></div>
        <div className="metric card"><div className="metric-value">{products.length - followed.length}</div><div className="muted small">Sin seguidores</div></div>
        <div className="metric card"><div className="metric-value">{products.filter((p) => p.status === "broken").length}</div><div className="muted small">Broken</div></div>
      </section>
      <div className="toolbar">
        <input type="search" className="grow" placeholder="Buscar producto…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar" />
        <select value={store} onChange={(e) => setStore(e.target.value)} aria-label="Tienda">
          <option value="">Todas las tiendas</option>
          {stores.map((s) => <option key={s} value={s}>{PROCESSOR_LABEL[s] ?? s}</option>)}
        </select>
      </div>
      <section className="card table-card">
        <table>
          <thead>
            <tr><th>Producto</th><th>Tienda</th><th className="num">Precio</th><th>Lo siguen</th><th>Revisado</th></tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td>
                  <a href={p.url} target="_blank" rel="noreferrer" className="cell-title">{p.title || p.url}</a>
                  <StockBadge product={p} />
                </td>
                <td className="nowrap">{PROCESSOR_LABEL[p.processor] ?? p.processor}</td>
                <td className="num nowrap">{formatPrice(p.price, p.currency)}</td>
                <td>
                  {p.followers.length === 0 ? <span className="muted">nadie</span> : (
                    <span className="people">
                      {p.followers.map((name) => <button key={name} className="person" onClick={() => onUser(name)}>{name}</button>)}
                    </span>
                  )}
                </td>
                <td className="small muted nowrap">{relative(p.last_checked_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="muted pad">Ningún producto coincide.</p>}
      </section>
    </>
  );
}

function UserWatches({ user, userId }) {
  const { data, error } = useAdminData([`/api/admin/watches?user_id=${userId}`]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Cargando…</p>;
  const [watches] = data;
  const active = watches.filter((w) => w.active).length;
  const notifs = watches.reduce((n, w) => n + w.notifications_7d, 0);
  const stores = new Set(watches.map((w) => w.product.processor)).size;

  return (
    <>
      <section className="metrics">
        <div className="metric card"><div className="metric-value">{watches.length}</div><div className="muted small">Productos</div></div>
        <div className="metric card"><div className="metric-value">{active}</div><div className="muted small">Activos</div></div>
        <div className="metric card"><div className="metric-value">{stores}</div><div className="muted small">Tiendas</div></div>
        <div className="metric card"><div className="metric-value">{notifs}</div><div className="muted small">Avisos (7 d)</div></div>
      </section>
      <section className="card table-card">
        {watches.length === 0 ? <p className="muted pad">{user?.username ?? "Este usuario"} no sigue productos.</p> : (
          <table>
            <thead>
              <tr><th>Producto</th><th>Tienda</th><th className="num">Precio</th><th className="num" title="Cambio de precio desde que empezó a seguirlo">Cambio</th><th>Reglas</th><th className="num">Avisos 7 d</th><th>Agregado</th></tr>
            </thead>
            <tbody>
              {watches.map((w) => {
                const p = w.product;
                return (
                  <tr key={w.id} className={w.active ? "" : "muted"}>
                    <td>
                      <a href={p.url} target="_blank" rel="noreferrer" className="cell-title">{p.title || p.url}</a>
                      <StockBadge product={{ status: p.status, available: p.current?.available }} />
                      {!w.active && <span className="badge paused-badge">Pausado</span>}
                    </td>
                    <td className="nowrap">{PROCESSOR_LABEL[p.processor] ?? p.processor}</td>
                    <td className="num nowrap">{formatPrice(p.current?.price, p.currency)}</td>
                    <td className="num nowrap"><Change from={w.price_at_start} to={p.current?.price} /></td>
                    <td>
                      <span className="rule-tags">
                        {w.rules.filter((r) => r.enabled).map((r) => <span key={r.id}>{ruleText(r, p.currency)}</span>)}
                        {w.rules.every((r) => !r.enabled) && <span className="muted">sin reglas</span>}
                      </span>
                    </td>
                    <td className="num" title={w.last_notification_at ? `Último aviso ${formatDate(w.last_notification_at)}` : "Sin avisos"}>{w.notifications_7d}</td>
                    <td className="small muted nowrap">{formatDate(w.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      <p className="muted small">
        <Link to="/admin/usuarios">Gestionar usuarios</Link>
      </p>
    </>
  );
}
