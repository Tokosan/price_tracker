import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import { dayLabel, formatDate, formatPrice, formatTime, PROCESSOR_LABEL } from "../format.js";

// Precio de la lectura anterior. Los avisos antiguos no guardaban `previous_price`:
// ahí solo PRICE_CHANGE lo trae (su `from` es la lectura anterior; el de PRICE_DROP
// y PRICE_UP es el último aviso, así que no sirve).
function previousPrice(p) {
  if (p.previous_price !== undefined) return p.previous_price;
  return p.fired.find((f) => f.kind === "PRICE_CHANGE")?.from ?? null;
}

const CHANNEL = { telegram: "Telegram", discord: "Discord" };

function Delivery({ delivery }) {
  const entries = Object.entries(delivery || {});
  if (entries.length === 0) return <span>Solo en la app</span>;
  return entries.map(([key, status], i) => {
    const name = CHANNEL[key.split(":")[0]] ?? key.split(":")[0];
    const ok = status === "ok";
    return (
      <span key={key} className={ok ? "" : "error"} title={ok ? undefined : status}>
        {i > 0 && " · "}
        {ok ? `Enviado por ${name}` : `${name}: no se pudo enviar`}
      </span>
    );
  });
}

export function NotificationItem({ n, link, logo }) {
  const p = n.payload;
  const prev = previousPrice(p);
  const diff = prev !== null && p.price != null && prev !== p.price ? p.price - prev : null;
  // Sin `link` es la lista del detalle del producto: el título sobra.
  const title = <Link to={`/w/${n.watch_id}`}>{p.title}</Link>;
  return (
    <li className="notif">
      {link && (
        n.product?.image_url
          ? <img className="notif-img" src={n.product.image_url} alt="" loading="lazy" />
          : <div className="notif-img" />
      )}
      <div className="notif-body">
        {link && <div className="notif-title">{title}</div>}
        <ul className="notif-fired">
          {p.fired.map((f, i) => <li key={i}>{f.message}</li>)}
          {p.historic_min && <li className="best">Mínimo histórico</li>}
        </ul>
        <div className="notif-meta">
          {link ? formatTime(n.sent_at) : formatDate(n.sent_at)}
          {link && n.product && (
            <>
              {" · "}
              <StoreLogo name={n.product.processor} url={logo} size={14} />
              {PROCESSOR_LABEL[n.product.processor] ?? n.product.processor}
            </>
          )}
          {" · "}
          <Delivery delivery={n.delivery} />
        </div>
      </div>
      <div className="notif-price">
        <div className="price">{formatPrice(p.price, p.currency)}</div>
        {p.available === false && <span className="badge out">Sin stock</span>}
        {diff !== null && (
          <div className={"small " + (diff < 0 ? "down" : "up")}>
            {diff < 0 ? "▼" : "▲"} {formatPrice(Math.abs(diff), p.currency)}
            <span className="muted"> · antes {formatPrice(prev, p.currency)}</span>
          </div>
        )}
        {p.list_price && p.price != null && p.list_price > p.price && (
          <div className="muted small">Precio normal {formatPrice(p.list_price, p.currency)}</div>
        )}
      </div>
    </li>
  );
}

// Agrupa por día ("Hoy", "Ayer", "28 sept") manteniendo el orden.
function byDay(items) {
  const groups = [];
  for (const n of items) {
    const label = dayLabel(n.sent_at);
    if (groups.at(-1)?.label !== label) groups.push({ label, items: [] });
    groups.at(-1).items.push(n);
  }
  return groups;
}

export default function Notifications() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const stores = useStores();
  useEffect(() => {
    api("/api/notifications?limit=200").then(setItems).catch((e) => setError(e.message));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!items) return <p className="muted">Cargando…</p>;
  return (
    <>
      <h1>Avisos</h1>
      {items.length === 0 ? (
        <p className="muted">Todavía no hay avisos. Aparecen aquí cuando se cumple alguna de tus reglas.</p>
      ) : (
        byDay(items).map((g) => (
          <section key={g.label} className="notif-day">
            <h2 className="day-label">{g.label}</h2>
            <ul className="notif-list">
              {g.items.map((n) => <NotificationItem key={n.id} n={n} link logo={stores[n.product?.processor]?.logo_url} />)}
            </ul>
          </section>
        ))
      )}
    </>
  );
}
