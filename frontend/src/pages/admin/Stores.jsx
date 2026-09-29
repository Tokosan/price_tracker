import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api.js";
import { formatDate, PROCESSOR_LABEL, relative } from "../../format.js";
import { useAdminData } from "./useAdmin.js";

export default function Stores() {
  const { data, error, run } = useAdminData(["/api/admin/stores", "/api/admin/products?status=broken", "/api/admin/anomalies"]);
  if (!data) return error ? <p className="error">{error}</p> : <p className="muted">Cargando…</p>;
  const [stores, broken, anomalies] = data;

  return (
    <>
      <h1>Tiendas</h1>
      {error && <p className="error">{error}</p>}
      <section className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Tienda</th><th className="num">Productos</th><th className="num">Seguimientos</th><th className="num">Usuarios</th>
              <th className="num">Con fallos</th><th className="num">Anomalías 7 d</th><th>Última lectura OK</th>
            </tr>
          </thead>
          <tbody>
            {stores.map((s) => (
              <tr key={s.name}>
                <td>
                  <div className="strong">{s.label}</div>
                  <div className="muted small">{s.domain.replace(/^www\./, "")} · cada {s.check_interval_hours} h</div>
                </td>
                <td className="num">{s.products}</td>
                <td className="num">{s.watches}</td>
                <td className="num">{s.users}</td>
                <td className="num">
                  {s.broken > 0 ? <span className="error">{s.broken} broken</span> : s.failing > 0 ? <span className="warn">{s.failing}</span> : <span className="muted">0</span>}
                </td>
                <td className="num">{s.anomalies_7d || <span className="muted">0</span>}</td>
                <td className="small nowrap">{s.last_ok_at ? relative(s.last_ok_at) : <span className="muted">nunca</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <MeliConnection />

      <section className="card">
        <h2>Productos broken</h2>
        {broken.length === 0 ? <p className="muted">Ninguno.</p> : (
          <table>
            <tbody>
              {broken.map((p) => (
                <tr key={p.id}>
                  <td><a href={p.url} target="_blank" rel="noreferrer">{p.title || p.url}</a><div className="small muted">{p.last_error}</div></td>
                  <td className="small">{PROCESSOR_LABEL[p.processor]} · {p.fail_count} fallos · lo siguen {p.followers.join(", ") || "nadie"} · {relative(p.last_checked_at)}</td>
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
        <span className={`store-status ${st.connected ? "ok" : "unknown"}`}>
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
