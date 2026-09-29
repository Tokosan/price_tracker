import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import { formatPrice, PROCESSOR_LABEL, relative } from "../format.js";

export function priceChange(watch) {
  const cur = watch.product.current?.price;
  const start = watch.price_at_start;
  if (cur == null || !start) return null;
  return ((cur - start) / start) * 100;
}

const storeLabel = (w) => PROCESSOR_LABEL[w.product.processor] ?? w.product.processor;
const title = (w) => w.product.title || w.product.url;
const byName = (a, b) => title(a).localeCompare(title(b), "es", { sensitivity: "base" });

// Cada orden define su dirección natural (la que se usa al elegirlo).
const SORTS = {
  created: { label: "Fecha de agregado", dir: "desc", cmp: (a, b) => a.created_at.localeCompare(b.created_at) },
  name: { label: "Nombre", dir: "asc", cmp: byName },
  price: { label: "Precio", dir: "asc", cmp: (a, b) => a.product.current.price - b.product.current.price },
  store: { label: "Tienda", dir: "asc", cmp: (a, b) => storeLabel(a).localeCompare(storeLabel(b), "es") || byName(a, b) },
};

const STATUS = {
  all: { label: "Todos los estados", test: () => true },
  available: { label: "Disponibles", test: (w) => w.product.current?.available === true },
  out: { label: "Sin stock", test: (w) => w.product.current?.available === false },
  down: { label: "Bajaron de precio", test: (w) => (priceChange(w) ?? 0) <= -0.5 },
  paused: { label: "Pausados", test: (w) => !w.active },
  broken: { label: "Con problemas", test: (w) => w.product.status === "broken" },
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
  const hasPrice = (w) => w.product.current?.price != null;
  return [...list].sort((a, b) => {
    if (sort === "price" && hasPrice(a) !== hasPrice(b)) return hasPrice(a) ? -1 : 1;
    if (sort === "price" && !hasPrice(a)) return byName(a, b);
    return sign * cmp(a, b);
  });
}

// [[tienda, watches]] en orden alfabético, conservando el orden dentro de cada grupo.
function groupByStore(list) {
  const groups = new Map();
  for (const w of list) {
    const key = storeLabel(w);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(w);
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b, "es"));
}

export default function Watches() {
  const [watches, setWatches] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useView();
  const storeInfo = useStores();
  useEffect(() => {
    api("/api/watches").then(setWatches).catch((e) => setError(e.message));
  }, []);

  const stores = useMemo(
    () => [...new Set((watches ?? []).map((w) => w.product.processor))].sort((a, b) => (PROCESSOR_LABEL[a] ?? a).localeCompare(PROCESSOR_LABEL[b] ?? b)),
    [watches],
  );
  const shown = useMemo(() => {
    if (!watches) return [];
    const q = view.q.trim().toLocaleLowerCase("es");
    const test = (STATUS[view.status] ?? STATUS.all).test;
    const filtered = watches.filter(
      (w) => (!view.store || w.product.processor === view.store) && test(w) && (!q || title(w).toLocaleLowerCase("es").includes(q)),
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

  return (
    <>
      <div className="row-between">
        <h1>Productos</h1>
        <Link className="button" to="/agregar">+ Agregar</Link>
      </div>

      <div className="toolbar">
        <input type="search" className="grow" placeholder="Buscar por nombre…" value={view.q} onChange={(e) => setView({ q: e.target.value })} aria-label="Buscar" />
        <select value={view.store} onChange={(e) => setView({ store: e.target.value })} aria-label="Tienda">
          <option value="">Todas las tiendas</option>
          {stores.map((s) => <option key={s} value={s}>{PROCESSOR_LABEL[s] ?? s}</option>)}
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

      <p className="muted small list-count">
        {filtering ? `${shown.length} de ${watches.length} productos` : `${watches.length} productos`}
        {filtering && (
          <button className="link" onClick={() => setView({ q: "", store: "", status: "all" })}>Limpiar filtros</button>
        )}
      </p>

      {shown.length === 0 && <p className="muted empty">Ningún producto coincide con los filtros.</p>}
      {groups.map(([label, items]) => (
        <section key={label ?? "all"}>
          {label && <h2 className="day-label">{label} · {items.length}</h2>}
          <ul className="watch-list">{items.map((w) => <WatchCard key={w.id} w={w} logo={storeInfo[w.product.processor]?.logo_url} />)}</ul>
        </section>
      ))}
    </>
  );
}

function WatchCard({ w, logo }) {
  const p = w.product;
  const change = priceChange(w);
  return (
    <li>
      <Link to={`/w/${w.id}`} className={"watch-card card" + (w.active ? "" : " paused")}>
        {p.image_url ? <img src={p.image_url} alt="" loading="lazy" /> : <div className="img-ph" />}
        <div className="watch-main">
          <div className="watch-title">{p.title || p.url}</div>
          <div className="muted small store-line">
            <StoreLogo name={p.processor} url={logo} size={16} />
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
}
