import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { formatDate, PROCESSOR_LABEL, relative } from "../format.js";

const METRIC_LABELS = {
  users: "Usuarios",
  active_users: "Usuarios activos",
  watches: "Productos seguidos",
  active_watches: "Seguimientos activos",
  products: "Productos distintos",
  broken_products: "Productos broken",
  failing_products: "Con fallos recientes",
  price_points_24h: "Lecturas (24 h)",
  notifications_7d: "Avisos (7 d)",
  anomalies_7d: "Anomalías (7 d)",
  pending_site_requests: "Sitios pedidos",
};

export default function Admin() {
  const [metrics, setMetrics] = useState(null);
  const [users, setUsers] = useState([]);
  const [requests, setRequests] = useState([]);
  const [broken, setBroken] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [newUser, setNewUser] = useState("");
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, u, r, b, a] = await Promise.all([
        api("/api/admin/metrics"),
        api("/api/admin/users"),
        api("/api/admin/site-requests"),
        api("/api/admin/products?status=broken"),
        api("/api/admin/anomalies"),
      ]);
      setMetrics(m);
      setUsers(u);
      setRequests(r);
      setBroken(b);
      setAnomalies(a);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (fn) => {
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const createUser = (e) => {
    e.preventDefault();
    run(async () => {
      const r = await api("/api/admin/users", { method: "POST", body: { username: newUser } });
      setInvite({ username: r.user.username, url: r.invite_url });
      setNewUser("");
    });
  };
  const reinvite = (u) => run(async () => {
    const r = await api(`/api/admin/users/${u.id}/invite`, { method: "POST" });
    setInvite({ username: u.username, url: r.invite_url });
  });
  const patchUser = (u, body) => run(() => api(`/api/admin/users/${u.id}`, { method: "PATCH", body }));
  const setQuota = (u) => {
    const q = prompt(`Cuota de productos para ${u.username}`, u.watch_quota);
    if (q !== null && q !== "") patchUser(u, { watch_quota: Number(q) });
  };

  return (
    <>
      <h1>Admin</h1>
      {error && <p className="error">{error}</p>}

      {metrics && (
        <section className="metrics">
          {Object.entries(METRIC_LABELS).map(([k, label]) => (
            <div key={k} className="metric card">
              <div className="metric-value">{metrics[k]}</div>
              <div className="muted small">{label}</div>
            </div>
          ))}
          <div className="metric card">
            <div className="small">
              {Object.entries(metrics.products_by_processor).map(([k, v]) => (
                <div key={k}>{PROCESSOR_LABEL[k] ?? k}: <b>{v}</b></div>
              ))}
            </div>
            <div className="muted small">Por sitio</div>
          </div>
        </section>
      )}

      <MeliConnection />

      <section className="card">
        <h2>Usuarios</h2>
        <form className="url-form" onSubmit={createUser}>
          <input placeholder="nuevo usuario" value={newUser} onChange={(e) => setNewUser(e.target.value)} />
          <button disabled={!newUser}>Crear e invitar</button>
        </form>
        {invite && (
          <div className="invite-box">
            <p>Link de invitación para <b>{invite.username}</b> (un solo uso, 48 h):</p>
            <code>{invite.url}</code>
            <button className="secondary" onClick={() => navigator.clipboard?.writeText(invite.url)}>Copiar</button>
          </div>
        )}
        <table>
          <thead>
            <tr><th>Usuario</th><th>Rol</th><th>Productos</th><th>Estado</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.active ? "" : "muted"}>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.watch_count} / <button className="link" onClick={() => setQuota(u)}>{u.watch_quota}</button></td>
                <td className="small">
                  {u.active ? "activo" : "desactivado"}
                  {!u.has_password && " · sin contraseña"}
                  {u.pending_invite_expires_at && ` · invitación hasta ${formatDate(u.pending_invite_expires_at)}`}
                </td>
                <td className="nowrap">
                  <button className="link" onClick={() => reinvite(u)}>{u.has_password ? "Reset" : "Nuevo link"}</button>
                  {u.role !== "admin" && (
                    <button className="link" onClick={() => patchUser(u, { active: !u.active })}>{u.active ? "Desactivar" : "Activar"}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Sitios pedidos</h2>
        {requests.length === 0 ? <p className="muted">Nada pendiente.</p> : (
          <table>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} className={r.status === "pending" ? "" : "muted"}>
                  <td><a href={r.url} target="_blank" rel="noreferrer">{r.url}</a><div className="small muted">{r.note}</div></td>
                  <td className="small">{r.username} · {formatDate(r.created_at)}</td>
                  <td className="nowrap">
                    {r.status === "pending" ? (
                      <>
                        <button className="link" onClick={() => run(() => api(`/api/admin/site-requests/${r.id}`, { method: "PATCH", body: { status: "done" } }))}>Hecho</button>
                        <button className="link" onClick={() => run(() => api(`/api/admin/site-requests/${r.id}`, { method: "PATCH", body: { status: "rejected" } }))}>Rechazar</button>
                      </>
                    ) : r.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Productos broken</h2>
        {broken.length === 0 ? <p className="muted">Ninguno. 🎉</p> : (
          <table>
            <tbody>
              {broken.map((p) => (
                <tr key={p.id}>
                  <td><a href={p.url} target="_blank" rel="noreferrer">{p.title || p.url}</a><div className="small muted">{p.last_error}</div></td>
                  <td className="small">{PROCESSOR_LABEL[p.processor]} · {p.fail_count} fallos · {p.watchers} lo siguen · {relative(p.last_checked_at)}</td>
                  <td><button className="link" onClick={() => run(() => api(`/api/admin/products/${p.id}/retry`, { method: "POST" }))}>Reintentar</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Anomalías</h2>
        {anomalies.length === 0 ? <p className="muted">Ninguna.</p> : (
          <table>
            <tbody>
              {anomalies.map((a) => (
                <tr key={a.id}>
                  <td><a href={a.product.url} target="_blank" rel="noreferrer">{a.product.title}</a></td>
                  <td className="small">{a.kind}: {a.detail}</td>
                  <td className="small nowrap">{formatDate(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

// Conexión OAuth con MercadoLibre: el admin aprueba la app una vez y el backend
// renueva el token solo. "Conectar" es una navegación (redirige a MercadoLibre).
function MeliConnection() {
  const [st, setSt] = useState(null);
  const [params, setParams] = useSearchParams();
  const result = params.get("meli");
  useEffect(() => {
    api("/api/admin/meli").then(setSt).catch(() => setSt(null));
  }, []);
  if (!st) return null;
  return (
    <section className="card">
      <div className="row-between">
        <h2>MercadoLibre</h2>
        <span className={`site-status ${st.connected ? "ok" : "unknown"}`}>
          {st.connected ? "Conectado" : "No conectado"}
        </span>
      </div>
      {result === "ok" && <p className="ok-msg">✅ Cuenta conectada.</p>}
      {result === "error" && <p className="error">No se pudo conectar: {params.get("msg")}</p>}
      {!st.configured ? (
        <p className="muted">Falta configurar MELI_CLIENT_ID y MELI_CLIENT_SECRET en el .env.</p>
      ) : (
        <>
          {st.connected && (
            <p className="small muted">
              Cuenta {st.account_id} · permisos: {st.scope || "—"} · el token vence {relative(st.expires_at)}
              {!st.can_refresh && " · ⚠ sin refresh token: habrá que reconectar cuando venza"}
            </p>
          )}
          <p className="small muted">
            La API de MercadoLibre exige una cuenta conectada (solo lectura). Se aprueba una vez y
            el token se renueva solo.
          </p>
          <a
            className={"button" + (st.connected ? " secondary" : "")}
            href="/api/admin/meli/connect"
            onClick={() => result && setParams({})}
          >
            {st.connected ? "Reconectar" : "Conectar MercadoLibre"}
          </a>
        </>
      )}
    </section>
  );
}
