import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { formatPrice, PROCESSOR_LABEL, relative } from "../format.js";

export function priceChange(watch) {
  const cur = watch.product.current?.price;
  const start = watch.price_at_start;
  if (cur == null || !start) return null;
  return ((cur - start) / start) * 100;
}

export default function Watches() {
  const [watches, setWatches] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/watches").then(setWatches).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!watches) return <p className="muted">Cargando…</p>;
  if (watches.length === 0)
    return (
      <div className="empty card">
        <h2>Aún no sigues ningún producto</h2>
        <p>
          Pega el link de un producto de alguna de las <Link to="/tiendas">tiendas soportadas</Link>.
        </p>
        <Link className="button" to="/agregar">Agregar producto</Link>
      </div>
    );

  return (
    <>
      <div className="row-between">
        <h1>Productos</h1>
        <Link className="button" to="/agregar">+ Agregar</Link>
      </div>
      <ul className="watch-list">
        {watches.map((w) => {
          const p = w.product;
          const change = priceChange(w);
          return (
            <li key={w.id}>
              <Link to={`/w/${w.id}`} className={"watch-card card" + (w.active ? "" : " paused")}>
                {p.image_url ? <img src={p.image_url} alt="" loading="lazy" /> : <div className="img-ph" />}
                <div className="watch-main">
                  <div className="watch-title">{p.title || p.url}</div>
                  <div className="muted small">
                    {PROCESSOR_LABEL[p.processor] ?? p.processor} · revisado {relative(p.last_checked_at)}
                    {!w.active && " · pausado"}
                  </div>
                  {p.status === "broken" && <div className="warn small">⚠ No se ha podido leer este producto últimamente.</div>}
                </div>
                <div className="watch-price">
                  <div className="price">{formatPrice(p.current?.price, p.currency)}</div>
                  {p.current && !p.current.available && <div className="badge out">Sin stock</div>}
                  {change !== null && Math.abs(change) >= 0.5 && (
                    <div className={"small " + (change < 0 ? "down" : "up")}>
                      {change < 0 ? "▼" : "▲"} {Math.abs(change).toFixed(0)} %
                    </div>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}
