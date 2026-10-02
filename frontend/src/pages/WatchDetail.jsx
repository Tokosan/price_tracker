import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useMe } from "../App.jsx";
import PriceChart from "../components/PriceChart.jsx";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import RulesEditor, { editorFromRules, rulesFromEditor } from "../components/RulesEditor.jsx";
import { formatDate, formatPrice, PROCESSOR_LABEL, relative, seriesColor } from "../format.js";
import { NotificationItem } from "./Notifications.jsx";

const storeName = (processor) => PROCESSOR_LABEL[processor] ?? processor;

// Links ordenados como en la tabla: los que cuentan y tienen stock primero, por precio.
function sortedItems(items) {
  const rank = (i) => (!i.counts ? 2 : i.current?.available && i.current.price != null ? 0 : 1);
  return [...items].sort((a, b) => rank(a) - rank(b) || (a.current?.price ?? Infinity) - (b.current?.price ?? Infinity));
}

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
  const [naming, setNaming] = useState(null);
  const stores = useStores();

  const load = useCallback(async () => {
    try {
      const [w, h, n] = await Promise.all([
        api(`/api/watches/${id}`),
        api(`/api/watches/${id}/history`),
        api(`/api/notifications?watch_id=${id}&limit=20`),
      ]);
      setWatch(w);
      setHistory(h.items);
      setNotifs(n);
      setEditor(editorFromRules(w.rules, w.currency));
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
  const currency = watch.currency;
  const multi = watch.items.length > 1;
  const best = watch.best;
  const bestItem = watch.items.find((i) => i.best) ?? watch.items[0];
  // Color por link según su orden en el Watch: no cambia al ocultar series ni al reordenar.
  const colorOf = Object.fromEntries(watch.items.map((i, n) => [i.id, seriesColor(n)]));

  const run = async (fn, okMsg) => {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await fn();
      if (okMsg) setMsg(okMsg);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const patch = (body, okMsg) =>
    run(async () => {
      const w = await api(`/api/watches/${id}`, { method: "PATCH", body });
      setWatch(w);
      setEditor(editorFromRules(w.rules, w.currency));
      setDirty(false);
    }, okMsg);

  const saveRules = () => {
    try {
      patch({ rules: rulesFromEditor(editor, currency) }, "Reglas guardadas.");
    } catch (e) {
      setError(e.message);
    }
  };

  const saveName = async (e) => {
    e.preventDefault();
    await patch({ name: naming }, "Nombre guardado.");
    setNaming(null);
  };

  const checkNow = () =>
    run(async () => {
      const r = await api(`/api/watches/${id}/check`, { method: "POST" });
      const o = r.outcome;
      setMsg(
        o.ok
          ? `Revisado: ${formatPrice(r.watch.best?.price, currency)}${o.notifications ? " · se generó un aviso" : ""}.`
          : o.anomaly
            ? "La lectura se veía rara y se descartó (quedó registrada para el admin)."
            : `No se pudo revisar: ${o.error}`,
      );
      await load();
    });

  const remove = async () => {
    if (!confirm("¿Dejar de seguir este producto? Se borran sus reglas y avisos.")) return;
    await api(`/api/watches/${id}`, { method: "DELETE" });
    navigate("/");
  };

  const cooldown = watch.manual_check_available_at && new Date(watch.manual_check_available_at) > new Date();
  // Etiqueta de cada link: la tienda (y su variante); numerada si la tienda se repite.
  const labelOf = {};
  const seen = {};
  for (const i of watch.items) {
    const base = storeName(i.processor) + (i.variant_label ? ` · ${i.variant_label}` : "");
    const repeated = watch.items.filter((j) => storeName(j.processor) + (j.variant_label ? ` · ${j.variant_label}` : "") === base).length > 1;
    seen[base] = (seen[base] ?? 0) + 1;
    labelOf[i.id] = repeated ? `${base} ${seen[base]}` : base;
  }
  const series = history.map((h) => ({
    key: h.product_id,
    label: labelOf[h.product_id] ?? storeName(h.processor),
    color: multi ? colorOf[h.product_id] : undefined,
    points: h.points,
  }));

  return (
    <>
      <div className="card detail-head">
        {bestItem?.image_url && <img src={bestItem.image_url} alt="" />}
        <div className="grow">
          {naming === null ? (
            <h1 className="watch-name">
              {watch.display_name}
              <button className="link" onClick={() => setNaming(watch.name ?? "")} title="Cambiar el nombre" aria-label="Cambiar el nombre">✎</button>
            </h1>
          ) : (
            <form className="name-form" onSubmit={saveName}>
              <input
                autoFocus
                value={naming}
                maxLength={200}
                placeholder={watch.items[0]?.title}
                onChange={(e) => setNaming(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setNaming(null)}
                aria-label="Nombre"
              />
              <button disabled={busy}>Guardar</button>
              <button type="button" className="secondary" onClick={() => setNaming(null)}>Cancelar</button>
              <span className="muted small">Vacío = el nombre de la tienda.</span>
            </form>
          )}
          {!multi && bestItem?.variant_label && <div className="small variant-label">Sigues: {bestItem.variant_label}</div>}
          {!multi && (
            <div className="muted small store-line">
              <StoreLogo name={bestItem.processor} url={stores[bestItem.processor]?.logo_url} size={16} />
              {storeName(bestItem.processor)} · <a href={bestItem.url} target="_blank" rel="noreferrer">ver en la tienda ↗</a>
            </div>
          )}
          <div className="price big">{formatPrice(best?.price, currency)}</div>
          <div className="small">
            {best && (best.available ? <span className="badge ok">Disponible</span> : <span className="badge out">Sin stock</span>)}
            {multi && best && <span className="muted"> · en {storeName(best.processor)}</span>}
            {best?.list_price > best?.price && <span className="muted"> · precio normal {formatPrice(best.list_price, currency)}</span>}
          </div>
          <div className="muted small">
            Al empezar: {formatPrice(watch.price_at_start, currency)} · mínimo visto: {formatPrice(watch.min_price, currency)}
          </div>
          {!multi && (
            <div className="muted small">
              Última revisión {relative(bestItem.last_checked_at)} · próxima {relative(bestItem.next_check_at)}
            </div>
          )}
          {!multi && bestItem.status === "broken" && <p className="warn">⚠ Este producto falló varias veces seguidas; el admin ya fue avisado.</p>}
        </div>
      </div>

      <div className="actions">
        <button onClick={checkNow} disabled={busy || cooldown}>
          {cooldown ? `Revisar ahora (disponible ${relative(watch.manual_check_available_at)})` : "Revisar ahora"}
        </button>
        <button className="secondary" onClick={() => patch({ active: !watch.active }, watch.active ? "Pausado." : "Reactivado.")} disabled={busy}>
          {watch.active ? "Pausar" : "Reactivar"}
        </button>
        <button className="danger" onClick={remove} disabled={busy}>Dejar de seguir</button>
      </div>
      {msg && <p className="ok-msg">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <Links watch={watch} colorOf={colorOf} labelOf={labelOf} stores={stores} busy={busy} run={run} onChange={load} navigate={navigate} />

      <section className="card">
        <h2>Historial de precios</h2>
        <PriceChart series={series} currency={currency} />
      </section>

      <section className="card">
        <h2>Avisarme cuando…</h2>
        {multi && <p className="muted small">Las reglas miran el mejor precio entre los links con stock.</p>}
        <RulesEditor value={editor} onChange={(v) => { setEditor(v); setDirty(true); }} currency={currency} />
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

// Tabla de links del Watch con sus acciones: agregar, mover a otro producto y quitar.
function Links({ watch, colorOf, labelOf, stores, busy, run, onChange, navigate }) {
  const [url, setUrl] = useState("");
  const [moving, setMoving] = useState(null); // product_id del link que se está moviendo
  const [targets, setTargets] = useState(null);
  const [target, setTarget] = useState("new");
  const currency = watch.currency;
  const multi = watch.items.length > 1;

  const add = (e) => {
    e.preventDefault();
    run(async () => {
      await api(`/api/watches/${watch.id}/items`, { method: "POST", body: { url } });
      setUrl("");
      await onChange();
    }, "Link agregado.");
  };

  const quit = (item) => {
    const last = watch.items.length === 1;
    const text = last
      ? "Es el único link: se deja de seguir el producto y se borran sus reglas y avisos. ¿Seguir?"
      : `¿Quitar el link de ${storeName(item.processor)}?`;
    if (!confirm(text)) return;
    run(async () => {
      const r = await api(`/api/watches/${watch.id}/items/${item.id}`, { method: "DELETE" });
      if (r.watch === null) navigate("/");
      else await onChange();
    }, last ? null : "Link quitado.");
  };

  const startMove = async (item) => {
    setMoving(item.id);
    setTarget(multi ? "new" : "");
    if (targets === null) {
      try {
        const all = await api("/api/watches");
        setTargets(all.filter((w) => w.id !== watch.id && w.currency === currency));
      } catch {
        setTargets([]);
      }
    }
  };

  const move = (item) => {
    const to = target === "new" ? null : Number(target);
    const dest = to === null ? null : targets.find((w) => w.id === to);
    const last = watch.items.length === 1;
    if (last && !confirm(`Es el único link: este producto se borra y el link pasa a «${dest?.display_name}». ¿Seguir?`)) return;
    run(async () => {
      const r = await api(`/api/watches/${watch.id}/items/${item.id}/move`, { method: "POST", body: { to } });
      setMoving(null);
      setTargets(null);
      if (r.source === null) navigate(`/w/${r.target.id}`);
      else await onChange();
    }, "Link movido.");
  };

  return (
    <section className="card table-card links-card">
      <h2>Links · {watch.items.length}</h2>
      <table className="links">
        <thead>
          <tr>
            <th>Tienda</th>
            <th className="num">Precio</th>
            <th className="num hide-sm">Normal</th>
            <th className="hide-sm">Revisado</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sortedItems(watch.items).map((i) => (
            <tr key={i.id} className={i.counts ? "" : "muted"}>
              <td>
                <div className="link-store">
                  {multi && <span className="swatch" style={{ "--series": colorOf[i.id] }} aria-hidden="true" />}
                  <StoreLogo name={i.processor} url={stores[i.processor]?.logo_url} size={18} />
                  <div>
                    <a href={i.url} target="_blank" rel="noreferrer" className="link-title">{i.title || i.url} ↗</a>
                    <div className="small muted">
                      {labelOf[i.id]}
                      {!i.counts && <> · <span className="badge muted-badge" title="Falló varias veces o no se lee hace mucho: no se usa para los avisos">no cuenta</span></>}
                      {i.status === "broken" && " · ⚠ con problemas"}
                    </div>
                  </div>
                </div>
              </td>
              <td className="num nowrap">
                <span className={i.best ? "strong" : ""}>{formatPrice(i.current?.price, currency)}</span>
                {i.current && !i.current.available && <div><span className="badge out">Sin stock</span></div>}
              </td>
              <td className="num nowrap hide-sm">{i.current?.list_price > i.current?.price ? formatPrice(i.current.list_price, currency) : "—"}</td>
              <td className="small nowrap hide-sm">{relative(i.last_checked_at)}</td>
              <td className="nowrap row-actions">
                {moving === i.id ? (
                  <span className="move-form">
                    <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Mover a">
                      {!multi && <option value="" disabled>Elige un producto…</option>}
                      {multi && <option value="new">Un producto nuevo (copia las reglas)</option>}
                      {(targets ?? []).map((w) => (
                        <option key={w.id} value={w.id} disabled={w.items.length >= 8}>
                          {w.display_name}{w.items.length >= 8 ? " (lleno)" : ""}
                        </option>
                      ))}
                    </select>
                    <button className="link" onClick={() => move(i)} disabled={busy || target === ""}>Mover</button>
                    <button className="link" onClick={() => setMoving(null)}>Cancelar</button>
                  </span>
                ) : (
                  <>
                    <button className="link" onClick={() => startMove(i)} disabled={busy}>Mover a…</button>
                    <button className="link danger-link" onClick={() => quit(i)} disabled={busy}>Quitar</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {watch.items.length < 8 ? (
        <form className="add-link" onSubmit={add}>
          <input
            type="url"
            required
            placeholder="Otro link de la misma cosa (otra tienda o publicación)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-label="Link"
          />
          <button disabled={busy || !url}>+ Agregar link</button>
        </form>
      ) : (
        <p className="muted small add-link">Este producto ya tiene el máximo de 8 links.</p>
      )}
      <p className="muted small add-link">Te avisamos por el más barato con stock.</p>
    </section>
  );
}
