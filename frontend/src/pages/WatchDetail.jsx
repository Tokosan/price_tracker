import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useMe } from "../App.jsx";
import PriceChart from "../components/PriceChart.jsx";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import RulesEditor, { editorFromRules, rulesFromEditor } from "../components/RulesEditor.jsx";
import { formatDate, formatPrice, PROCESSOR_LABEL, relative } from "../format.js";
import { NotificationItem } from "./Notifications.jsx";

export default function WatchDetail() {
  const { id } = useParams();
  const { me } = useMe();
  const navigate = useNavigate();
  const [watch, setWatch] = useState(null);
  const [history, setHistory] = useState([]);
  const [notifs, setNotifs] = useState([]);
  const [editor, setEditor] = useState({});
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const stores = useStores();

  const load = useCallback(async () => {
    try {
      const [w, h, n] = await Promise.all([
        api(`/api/watches/${id}`),
        api(`/api/watches/${id}/history`),
        api(`/api/notifications?watch_id=${id}&limit=20`),
      ]);
      setWatch(w);
      setHistory(h);
      setNotifs(n);
      setEditor(editorFromRules(w.rules, w.product.currency));
      setDirty(false);
    } catch (e) {
      setError(e.message);
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  if (error && !watch) return <p className="error">{error}</p>;
  if (!watch) return <p className="muted">Cargando…</p>;
  const p = watch.product;

  const patch = async (body, okMsg) => {
    setBusy(true);
    setError("");
    try {
      const w = await api(`/api/watches/${id}`, { method: "PATCH", body });
      setWatch(w);
      setEditor(editorFromRules(w.rules, w.product.currency));
      setDirty(false);
      setMsg(okMsg);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveRules = () => {
    try {
      patch({ rules: rulesFromEditor(editor, p.currency) }, "Reglas guardadas.");
    } catch (e) {
      setError(e.message);
    }
  };

  const checkNow = async () => {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const r = await api(`/api/watches/${id}/check`, { method: "POST" });
      const o = r.outcome;
      setMsg(
        o.ok
          ? `Revisado: ${formatPrice(r.watch.product.current?.price, p.currency)}${o.notifications ? " · se generó un aviso" : ""}.`
          : o.anomaly
            ? "La lectura se veía rara y se descartó (quedó registrada para el admin)."
            : `No se pudo revisar: ${o.error}`,
      );
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm("¿Dejar de seguir este producto? Se borran sus reglas y avisos.")) return;
    await api(`/api/watches/${id}`, { method: "DELETE" });
    navigate("/");
  };

  const cooldown = p.manual_check_available_at && new Date(p.manual_check_available_at) > new Date();
  const cur = p.current;

  return (
    <>
      <div className="card detail-head">
        {p.image_url && <img src={p.image_url} alt="" />}
        <div className="grow">
          <h1>{p.title}</h1>
          <div className="muted small store-line">
            <StoreLogo name={p.processor} url={stores[p.processor]?.logo_url} size={16} />
            {PROCESSOR_LABEL[p.processor] ?? p.processor} · <a href={p.url} target="_blank" rel="noreferrer">ver en la tienda ↗</a>
          </div>
          <div className="price big">{formatPrice(cur?.price, p.currency)}</div>
          <div className="small">
            {cur && (cur.available ? <span className="badge ok">Disponible</span> : <span className="badge out">Sin stock</span>)}
            {cur?.list_price > cur?.price && <span className="muted"> · precio normal {formatPrice(cur.list_price, p.currency)}</span>}
          </div>
          <div className="muted small">
            Al empezar: {formatPrice(watch.price_at_start, p.currency)} · mínimo visto: {formatPrice(p.min_price, p.currency)}
          </div>
          <div className="muted small">
            Última revisión {relative(p.last_checked_at)} · próxima {relative(p.next_check_at)}
          </div>
          {p.status === "broken" && <p className="warn">⚠ Este producto falló varias veces seguidas; el admin ya fue avisado.</p>}
        </div>
      </div>

      <div className="actions">
        <button onClick={checkNow} disabled={busy || cooldown}>
          {cooldown ? `Revisar ahora (disponible ${relative(p.manual_check_available_at)})` : "Revisar ahora"}
        </button>
        <button className="secondary" onClick={() => patch({ active: !watch.active }, watch.active ? "Pausado." : "Reactivado.")} disabled={busy}>
          {watch.active ? "Pausar" : "Reactivar"}
        </button>
        <button className="danger" onClick={remove} disabled={busy}>Dejar de seguir</button>
      </div>
      {msg && <p className="ok-msg">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <section className="card">
        <h2>Historial de precios</h2>
        <PriceChart points={history} currency={p.currency} />
      </section>

      <section className="card">
        <h2>Avisarme cuando…</h2>
        <RulesEditor value={editor} onChange={(v) => { setEditor(v); setDirty(true); }} currency={p.currency} />
        <button onClick={saveRules} disabled={busy || !dirty}>Guardar reglas</button>
        <div className="channel-toggle">
          {Object.keys(watch.channels || {}).length > 0 ? (
            Object.entries(watch.channels).map(([kind, enabled]) => (
              <label className="check" key={kind}>
                <input type="checkbox" checked={enabled} onChange={(e) => patch({ channels: { [kind]: e.target.checked } }, "Canal actualizado.")} />
                Enviar los avisos de este producto por {kind === "telegram" ? "Telegram" : "Discord"}
              </label>
            ))
          ) : (
            <p className="muted small">
              {me.telegram.configured
                ? "Conecta Telegram o Discord en Ajustes para recibir avisos fuera de la app."
                : "Telegram no configurado: conecta Discord en Ajustes o revisa los avisos en la pestaña Avisos."}
            </p>
          )}
        </div>
      </section>

      <section className="card">
        <h2>Avisos de este producto</h2>
        {notifs.length === 0 ? <p className="muted">Todavía no hay avisos.</p> : (
          <ul className="notif-list">{notifs.map((n) => <NotificationItem key={n.id} n={n} />)}</ul>
        )}
        <p className="muted small">Siguiendo desde {formatDate(watch.created_at)}</p>
      </section>
    </>
  );
}
