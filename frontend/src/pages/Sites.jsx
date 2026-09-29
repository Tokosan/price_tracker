import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { relative } from "../format.js";

const STATUS = {
  ok: { label: "Funcionando", cls: "ok" },
  problems: { label: "Con problemas", cls: "problems" },
  unknown: { label: "Sin lecturas aún", cls: "unknown" },
};

// Color estable por sitio para el ícono con la inicial.
function hue(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

function every(hours) {
  return hours % 24 === 0 && hours >= 24 ? `cada ${hours / 24} d` : `cada ${hours} h`;
}

export default function Sites() {
  const [sites, setSites] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/processors").then(setSites).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!sites) return <p className="muted">Cargando…</p>;

  return (
    <>
      <h1>Sitios soportados</h1>
      <p className="muted">
        Pega el link de un producto de cualquiera de estas tiendas en{" "}
        <Link to="/agregar">Agregar</Link>.
      </p>
      <ul className="site-grid">
        {sites.map((s) => {
          const st = STATUS[s.status] ?? STATUS.unknown;
          return (
            <li key={s.name} className="card site-card">
              <div className="site-head">
                <span className="site-icon" style={{ "--h": hue(s.name) }} aria-hidden="true">
                  {s.label.charAt(0)}
                </span>
                <div className="grow">
                  <h2>{s.label}</h2>
                  <a href={s.home_url} target="_blank" rel="noreferrer" className="muted small">
                    {s.domain.replace(/^www\./, "")}
                  </a>
                </div>
                <span
                  className={`site-status ${st.cls}`}
                  title={s.last_ok_at ? `Última lectura correcta ${relative(s.last_ok_at)}` : undefined}
                >
                  {st.label}
                </span>
              </div>

              <ul className="chips">
                <li>Precio</li>
                <li>Stock</li>
                {s.supports_list_price && <li>Precio antes de oferta</li>}
                {s.supports_variants && <li>Variantes</li>}
                {s.slow && <li className="slow">Lectura lenta</li>}
              </ul>

              <dl className="site-facts">
                <div>
                  <dt>Revisión</dt>
                  <dd>{every(s.check_interval_hours)}</dd>
                </div>
                <div>
                  <dt>Plataforma</dt>
                  <dd>{s.platform || "—"}</dd>
                </div>
                <div>
                  <dt>Tus productos</dt>
                  <dd>{s.my_watches}</dd>
                </div>
              </dl>

              {s.notes && <p className="small site-notes">{s.notes}</p>}

              {s.example_url && (
                <Link className="button secondary" to={`/agregar?url=${encodeURIComponent(s.example_url)}`}>
                  Probar con un ejemplo
                </Link>
              )}
            </li>
          );
        })}
      </ul>
      <RequestSite />
    </>
  );
}

function RequestSite() {
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/site-requests", { method: "POST", body: { url, note } });
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>¿Falta una tienda?</h2>
      {done ? (
        <p>✅ Listo, el admin verá tu pedido.</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <label>
            Link de un producto de esa tienda
            <input type="url" required placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          </label>
          <label>
            Nota (opcional)
            <input value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
          </label>
          {error && <p className="error">{error}</p>}
          <button disabled={busy || url.length < 8}>{busy ? "Enviando…" : "Pedir esta tienda"}</button>
        </form>
      )}
    </div>
  );
}
