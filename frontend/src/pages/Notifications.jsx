import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { formatDate, formatPrice } from "../format.js";

export function NotificationItem({ n, link }) {
  const p = n.payload;
  const delivery = Object.entries(n.delivery || {});
  return (
    <li className="notif">
      <div className="row-between">
        <b>{link ? <Link to={`/w/${n.watch_id}`}>{p.title}</Link> : p.title}</b>
        <span className="muted small">{formatDate(n.sent_at)}</span>
      </div>
      <div>
        {formatPrice(p.price, p.currency)}
        {p.list_price && p.list_price > p.price && <span className="muted"> (antes {formatPrice(p.list_price, p.currency)})</span>}
        {p.historic_min && <span className="badge ok"> Mínimo histórico</span>}
      </div>
      <ul className="fired">
        {p.fired.map((f, i) => <li key={i}>{f.message}</li>)}
      </ul>
      <div className="muted small">
        {delivery.length === 0 ? "Solo en la app" : delivery.map(([k, v]) => `${k.split(":")[0]}: ${v}`).join(" · ")}
      </div>
    </li>
  );
}

export default function Notifications() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
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
        <ul className="notif-list card">{items.map((n) => <NotificationItem key={n.id} n={n} link />)}</ul>
      )}
    </>
  );
}
