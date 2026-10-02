import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import { formatPrice, PROCESSOR_LABEL, relative } from "../format.js";

// Máximo de links por producto (igual que el backend).
const MAX_ITEMS = 8;

export function priceChange(watch) {
  const cur = watch.best?.price;
  const start = watch.price_at_start;
  if (cur == null || !start) return null;
  return ((cur - start) / start) * 100;
}

const processorsOf = (w) => [...new Set(w.items.map((i) => i.processor))];
const label = (proc) => PROCESSOR_LABEL[proc] ?? proc;
// Un producto con links en varias tiendas va en su propia sección al agrupar por tienda:
// bajo la tienda ganadora cambiaría de sección cada vez que cambia el más barato.
const MULTI = "Varias tiendas";
const storeLabel = (w) => {
  const procs = processorsOf(w);
  return procs.length === 1 ? label(procs[0]) : MULTI;
};
const title = (w) => w.display_name || w.items[0]?.url || "";
const byName = (a, b) => title(a).localeCompare(title(b), "es", { sensitivity: "base" });

// Cada orden define su dirección natural (la que se usa al elegirlo).
const SORTS = {
  created: { label: "Fecha de agregado", dir: "desc", cmp: (a, b) => a.created_at.localeCompare(b.created_at) },
  name: { label: "Nombre", dir: "asc", cmp: byName },
  price: { label: "Precio", dir: "asc", cmp: (a, b) => a.best.price - b.best.price },
  store: { label: "Tienda", dir: "asc", cmp: (a, b) => storeLabel(a).localeCompare(storeLabel(b), "es") || byName(a, b) },
};

const STATUS = {
  all: { label: "Todos los estados", test: () => true },
  available: { label: "Disponibles", test: (w) => w.best?.available === true },
  out: { label: "Sin stock", test: (w) => w.best?.available === false },
  down: { label: "Bajaron de precio", test: (w) => (priceChange(w) ?? 0) <= -0.5 },
  paused: { label: "Pausados", test: (w) => !w.active },
  broken: { label: "Con problemas", test: (w) => w.items.some((i) => i.status === "broken") },
};

const DEFAULT_VIEW = { q: "", store: "", status: "all", sort: "created", dir: "desc", group: false };
const VIEW_KEY = "tracker_watches_view";

// La vista (filtros, orden, agrupación) se recuerda en este navegador.
function useView() {
  const [view, setView] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(VIEW_KEY));
      return { ...DEFAULT_VIEW, ...saved, q: "" };
    } catch {
      return DEFAULT_VIEW;
    }
  });
  const update = (patch) => {
    const next = { ...view, ...patch };
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify({ ...next, q: "" }));
    } catch {
      // Sin storage: la vista solo dura esta visita.
    }
  };
  return [view, update];
}

function sortWatches(list, sort, dir) {
  const { cmp } = SORTS[sort] ?? SORTS.created;
  const sign = dir === "desc" ? -1 : 1;
  // Sin precio al final, en cualquier dirección.
  const hasPrice = (w) => w.best?.price != null;
  return [...list].sort((a, b) => {
    if (sort === "price" && hasPrice(a) !== hasPrice(b)) return hasPrice(a) ? -1 : 1;
    if (sort === "price" && !hasPrice(a)) return byName(a, b);
    return sign * cmp(a, b);
  });
}

// [[tienda, watches]] en orden alfabético ("Varias tiendas" al final), conservando el
// orden dentro de cada grupo.
function groupByStore(list) {
  const groups = new Map();
  for (const w of list) {
    const key = storeLabel(w);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(w);
  }
  return [...groups].sort(([a], [b]) => (a === MULTI) - (b === MULTI) || a.localeCompare(b, "es"));
}

export default function Watches() {
  const [watches, setWatches] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useView();
  const [params, setParams] = useSearchParams();
  const selecting = params.has("seleccionar");
  const [selected, setSelected] = useState(() => new Set());
  const [merging, setMerging] = useState(false);
  const storeInfo = useStores();
  useEffect(() => {
    api("/api/watches").then(setWatches).catch((e) => setError(e.message));
  }, []);

  const stores = useMemo(
    () => [...new Set((watches ?? []).flatMap(processorsOf))].sort((a, b) => label(a).localeCompare(label(b))),
    [watches],
  );
  const shown = useMemo(() => {
    if (!watches) return [];
    const q = view.q.trim().toLocaleLowerCase("es");
    const test = (STATUS[view.status] ?? STATUS.all).test;
    // La búsqueda mira el nombre puesto y el título de cada link.
    const matches = (w) => [title(w), ...w.items.map((i) => i.title || "")].some((t) => t.toLocaleLowerCase("es").includes(q));
    const filtered = watches.filter(
      (w) => (!view.store || processorsOf(w).includes(view.store)) && test(w) && (!q || matches(w)),
    );
    return sortWatches(filtered, view.sort, view.dir);
  }, [watches, view]);

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

  const groups = view.group ? groupByStore(shown) : [[null, shown]];
  const filtering = view.q || view.store || view.status !== "all";
  const setSelecting = (on) => {
    setSelected(new Set());
    setMerging(false);
    setParams(on ? { seleccionar: "1" } : {}, { replace: true });
  };
  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
    setMerging(false);
  };
  const chosen = watches.filter((w) => selected.has(w.id));

  return (
    <>
      <div className="row-between">
        <h1>Productos</h1>
        <div className="actions-inline">
          {watches.length > 1 && (
            <button className="secondary" onClick={() => setSelecting(!selecting)}>
              {selecting ? "Cancelar" : "Seleccionar"}
            </button>
          )}
          <Link className="button" to="/agregar">+ Agregar</Link>
        </div>
      </div>

      <div className="toolbar">
        <input type="search" className="grow" placeholder="Buscar por nombre…" value={view.q} onChange={(e) => setView({ q: e.target.value })} aria-label="Buscar" />
        <select value={view.store} onChange={(e) => setView({ store: e.target.value })} aria-label="Tienda">
          <option value="">Todas las tiendas</option>
          {stores.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <select value={view.status} onChange={(e) => setView({ status: e.target.value })} aria-label="Estado">
          {Object.entries(STATUS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </select>
        <div className="sort">
          <select value={view.sort} onChange={(e) => setView({ sort: e.target.value, dir: SORTS[e.target.value].dir })} aria-label="Ordenar por">
            {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
          </select>
          <button
            className="secondary icon-only"
            onClick={() => setView({ dir: view.dir === "asc" ? "desc" : "asc" })}
            title={view.dir === "asc" ? "Ascendente" : "Descendente"}
            aria-label={view.dir === "asc" ? "Orden ascendente" : "Orden descendente"}
          >
            {view.dir === "asc" ? "↑" : "↓"}
          </button>
        </div>
        <label className="check toggle">
          <input type="checkbox" checked={view.group} onChange={(e) => setView({ group: e.target.checked })} />
          Agrupar por tienda
        </label>
      </div>

      {selecting && (
        <p className="muted small select-hint">
          Elige los productos que son la misma cosa (por ejemplo, el mismo juego en dos tiendas) para seguirlos como uno solo.
        </p>
      )}

      <p className="muted small list-count">
        {filtering ? `${shown.length} de ${watches.length} productos` : `${watches.length} productos`}
        {filtering && (
          <button className="link" onClick={() => setView({ q: "", store: "", status: "all" })}>Limpiar filtros</button>
        )}
      </p>

      {shown.length === 0 && <p className="muted empty">Ningún producto coincide con los filtros.</p>}
      {groups.map(([group, items]) => (
        <section key={group ?? "all"}>
          {group && <h2 className="day-label">{group} · {items.length}</h2>}
          <ul className="watch-list">
            {items.map((w) => (
              <WatchCard
                key={w.id}
                w={w}
                stores={storeInfo}
                selecting={selecting}
                selected={selected.has(w.id)}
                onToggle={() => toggle(w.id)}
                onChange={(next) => setWatches(watches.map((x) => (x.id === next.id ? next : x)))}
                onRemove={() => setWatches(watches.filter((x) => x.id !== w.id))}
              />
            ))}
          </ul>
        </section>
      ))}

      {selecting && (
        <div className="select-bar card">
          {merging ? (
            <MergeDialog watches={chosen} onCancel={() => setMerging(false)} />
          ) : (
            <MergeBar chosen={chosen} onMerge={() => setMerging(true)} />
          )}
        </div>
      )}
    </>
  );
}

// Por qué no se pueden juntar los elegidos (o null si se puede).
function mergeProblem(chosen) {
  if (chosen.length < 2) return "Elige al menos dos productos.";
  const links = chosen.reduce((n, w) => n + w.items.length, 0);
  if (links > MAX_ITEMS) return `Entre todos suman ${links} links; el máximo es ${MAX_ITEMS}.`;
  if (new Set(chosen.map((w) => w.currency)).size > 1) return "Tienen monedas distintas.";
  return null;
}

function MergeBar({ chosen, onMerge }) {
  const problem = mergeProblem(chosen);
  return (
    <div className="row-between">
      <span className="small">
        {chosen.length === 0 ? "Ningún producto elegido" : `${chosen.length} elegido${chosen.length === 1 ? "" : "s"}`}
        {chosen.length > 0 && problem && <span className="muted"> · {problem}</span>}
      </span>
      <button onClick={onMerge} disabled={problem !== null}>Juntar ({chosen.length})</button>
    </div>
  );
}

// Confirmación: cuál conserva nombre, reglas y canales (por defecto, el más antiguo).
function MergeDialog({ watches, onCancel }) {
  const navigate = useNavigate();
  const oldest = [...watches].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
  const [primary, setPrimary] = useState(oldest.id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const others = watches.filter((w) => w.id !== primary && w.rules.length > 0);

  const merge = async () => {
    setBusy(true);
    setError("");
    try {
      const w = await api("/api/watches/merge", { method: "POST", body: { ids: watches.map((x) => x.id), primary } });
      navigate(`/w/${w.id}`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="merge-dialog">
      <h2>Juntar {watches.length} productos</h2>
      <p className="muted small">Se seguirán como uno solo y te avisaremos por el más barato con stock. ¿Cuál conserva su nombre, reglas y canales?</p>
      <ul className="merge-options">
        {watches.map((w) => (
          <li key={w.id}>
            <label className="check">
              <input type="radio" name="primary" checked={primary === w.id} onChange={() => setPrimary(w.id)} />
              <span>
                {title(w)}
                <span className="muted small"> · {w.rules.length} regla{w.rules.length === 1 ? "" : "s"} · {w.items.length} link{w.items.length === 1 ? "" : "s"}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {others.length > 0 && (
        <p className="warn small">Se descartan las reglas de: {others.map(title).join(", ")}. Sus avisos pasados se conservan.</p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button onClick={merge} disabled={busy}>{busy ? "Juntando…" : "Juntar"}</button>
        <button className="secondary" onClick={onCancel} disabled={busy}>Volver</button>
      </div>
    </div>
  );
}

// Menú ⋯ de una tarjeta: renombrar y dejar de seguir sin entrar al producto.
function CardMenu({ w, onRename, onRemove }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const pick = (fn) => () => {
    setOpen(false);
    fn();
  };
  return (
    <div className="card-menu" ref={ref}>
      <button className="icon-button" onClick={() => setOpen(!open)} aria-label={`Opciones de ${title(w)}`} aria-expanded={open} title="Opciones">⋯</button>
      {open && (
        <div className="menu-popover" role="menu">
          <button role="menuitem" onClick={pick(onRename)}>Renombrar</button>
          <button role="menuitem" className="danger-item" onClick={pick(onRemove)}>Dejar de seguir</button>
        </div>
      )}
    </div>
  );
}

function WatchCard({ w, stores, selecting, selected, onToggle, onChange, onRemove }) {
  const [naming, setNaming] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const saveName = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onChange(await api(`/api/watches/${w.id}`, { method: "PATCH", body: { name: naming } }));
      setNaming(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm(`¿Dejar de seguir «${title(w)}»? Se borran sus reglas y avisos.`)) return;
    try {
      await api(`/api/watches/${w.id}`, { method: "DELETE" });
      onRemove();
    } catch (err) {
      setError(err.message);
    }
  };

  const first = w.items[0] ?? {};
  const best = w.items.find((i) => i.best) ?? first;
  const procs = processorsOf(w);
  const multi = w.items.length > 1;
  const change = priceChange(w);
  const checked = w.items.map((i) => i.last_checked_at).filter(Boolean).sort().at(-1);
  const body = (
    <>
      {selecting && <input type="checkbox" className="card-check" checked={selected} onChange={onToggle} aria-label={`Elegir ${title(w)}`} />}
      {best.image_url ? <img src={best.image_url} alt="" loading="lazy" /> : <div className="img-ph" />}
      <div className="watch-main">
        {naming === null ? (
          <div className="watch-title">{title(w)}</div>
        ) : (
          <form className="name-form card-name-form" onSubmit={saveName}>
            <input
              autoFocus
              value={naming}
              maxLength={200}
              placeholder={first.title}
              onChange={(e) => setNaming(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setNaming(null)}
              aria-label="Nombre"
            />
            <button disabled={busy}>Guardar</button>
            <button type="button" className="secondary" onClick={() => setNaming(null)}>Cancelar</button>
          </form>
        )}
        {error && <div className="error small">{error}</div>}
        {!multi && first.variant_label && <div className="small variant-label">{first.variant_label}</div>}
        <div className="muted small store-line">
          {procs.slice(0, 3).map((p) => <StoreLogo key={p} name={p} url={stores[p]?.logo_url} size={16} />)}
          {procs.length === 1 ? label(procs[0]) : `${procs.length} tiendas`}
          {multi && <span className="badge links-badge">{w.items.length} links</span>}
          {" · "}revisado {relative(checked)}
          {!w.active && " · pausado"}
        </div>
        {w.items.some((i) => i.status === "broken") && (
          <div className="warn small">⚠ {multi ? "Un link no se ha podido leer" : "No se ha podido leer este producto"} últimamente.</div>
        )}
      </div>
      <div className="watch-price">
        <div className="price">{formatPrice(w.best?.price, w.currency)}</div>
        {multi && w.best && <div className="muted small">en {label(w.best.processor)}</div>}
        {w.best && !w.best.available && <div className="badge out">Sin stock</div>}
        {change !== null && Math.abs(change) >= 0.5 && (
          <div className={"small " + (change < 0 ? "down" : "up")}>
            {change < 0 ? "▼" : "▲"} {Math.abs(change).toFixed(0)} %
          </div>
        )}
      </div>
    </>
  );
  const cls = "watch-card card" + (w.active ? "" : " paused") + (selected ? " selected" : "");
  return (
    <li className="watch-item">
      {selecting ? (
        <label className={cls}>{body}</label>
      ) : naming !== null ? (
        // Renombrando: la tarjeta deja de ser un link para poder escribir.
        <div className={cls}>{body}</div>
      ) : (
        <Link to={`/w/${w.id}`} className={cls}>{body}</Link>
      )}
      {!selecting && naming === null && (
        <CardMenu w={w} onRename={() => setNaming(w.name ?? "")} onRemove={remove} />
      )}
    </li>
  );
}
