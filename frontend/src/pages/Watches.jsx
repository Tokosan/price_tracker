import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { CategoryChip, CategoryDot, CategoryManager, CategoryPicker, useCategories, useDismiss } from "../components/Categories.jsx";
import StoreLogo, { useStores } from "../components/StoreLogo.jsx";
import { formatPrice, PROCESSOR_LABEL, relative } from "../format.js";

// Máximo de links por producto (igual que el backend).
const MAX_ITEMS = 8;
// Chips de categoría en una tarjeta; el resto va como "+N".
const MAX_CHIPS = 3;

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
  available: { label: "Disponibles", test: (w) => w.best?.available === true },
  out: { label: "Sin stock", test: (w) => w.best?.available === false },
  down: { label: "Bajaron de precio", test: (w) => (priceChange(w) ?? 0) <= -0.5 },
  paused: { label: "Pausados", test: (w) => !w.active },
  broken: { label: "Con problemas", test: (w) => w.items.some((i) => i.status === "broken") },
};

const GROUPS = { "": "Sin agrupar", store: "Agrupar por tienda", category: "Agrupar por categoría" };
// En el filtro de categorías, "sin categoría" va junto a los id.
const NONE = "none";
const NO_CATEGORY = "Sin categoría";
// Tiendas visibles en la sidebar antes de "Ver todas".
const STORES_SHOWN = 8;

const DEFAULT_VIEW = {
  q: "",
  stores: [],
  statuses: [],
  cats: [],
  catMode: "any", // any (alguna) | all (todas)
  layout: "list", // list | grid (tarjetas)
  sort: "created",
  dir: "desc",
  group: "",
  collapsed: {},
};
const VIEW_KEY = "tracker_watches_view";

// Vistas guardadas antes de la sidebar: tienda y estado eran de un solo valor, y agrupar
// un checkbox (por tienda).
function upgradeView(saved) {
  const out = { ...saved };
  if (typeof saved.store === "string") out.stores = saved.store ? [saved.store] : [];
  if (typeof saved.status === "string") out.statuses = saved.status === "all" ? [] : [saved.status];
  if (typeof saved.group === "boolean") out.group = saved.group ? "store" : "";
  delete out.store;
  delete out.status;
  return out;
}

// La vista (filtros, orden, agrupación) se recuerda en este navegador.
function useView() {
  const [view, setView] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(VIEW_KEY));
      return { ...DEFAULT_VIEW, ...(saved && upgradeView(saved)), q: "" };
    } catch {
      return DEFAULT_VIEW;
    }
  });
  const update = (patch) => {
    setView((cur) => {
      const next = { ...cur, ...patch };
      try {
        localStorage.setItem(VIEW_KEY, JSON.stringify({ ...next, q: "" }));
      } catch {
        // Sin storage: la vista solo dura esta visita.
      }
      return next;
    });
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

// [[grupo, watches]] en orden alfabético (el grupo comodín al final), conservando el
// orden dentro de cada grupo. `keys` da los grupos de un watch (puede ir en varios).
function groupBy(list, keys, last) {
  const groups = new Map();
  for (const w of list) {
    for (const key of keys(w)) {
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(w);
    }
  }
  return [...groups].sort(([a], [b]) => (a === last) - (b === last) || a.localeCompare(b, "es"));
}

const toggled = (list, value, on) => (on ? [...new Set([...list, value])] : list.filter((x) => x !== value));

export default function Watches() {
  const [watches, setWatches] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useView();
  const [params, setParams] = useSearchParams();
  const selecting = params.has("seleccionar");
  const [selected, setSelected] = useState(() => new Set());
  const [merging, setMerging] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const storeInfo = useStores();
  const cats = useCategories();
  useEffect(() => {
    api("/api/watches").then(setWatches).catch((e) => setError(e.message));
  }, []);

  const catById = useMemo(() => new Map((cats.categories ?? []).map((c) => [c.id, c])), [cats.categories]);
  // Las categorías de un watch con su nombre y color al día (renombrar no recarga la lista);
  // antes de cargar las categorías, las que vienen en el watch.
  const catsOf = useCallback(
    (w) =>
      (cats.categories ? w.categories.map((c) => catById.get(c.id)).filter(Boolean) : [...w.categories]).sort((a, b) =>
        a.name.localeCompare(b.name, "es", { sensitivity: "base" }),
      ),
    [cats.categories, catById],
  );
  // Un filtro guardado puede nombrar una categoría que ya no existe.
  const activeCats = cats.categories ? view.cats.filter((c) => c === NONE || catById.has(c)) : view.cats;
  const catMode = view.catMode === "all" ? "all" : "any";

  const { shown, facets } = useMemo(() => {
    if (!watches) return { shown: [], facets: {} };
    const q = view.q.trim().toLocaleLowerCase("es");
    // La búsqueda mira el nombre puesto y el título de cada link.
    const matches = (w) => [title(w), ...w.items.map((i) => i.title || "")].some((t) => t.toLocaleLowerCase("es").includes(q));
    const idsOf = (w) => w.categories.map((c) => c.id);
    const hasCat = (w, c) => (c === NONE ? catsOf(w).length === 0 : idsOf(w).includes(c));
    const tests = {
      q: (w) => !q || matches(w),
      stores: (w) => !view.stores.length || processorsOf(w).some((p) => view.stores.includes(p)),
      statuses: (w) => !view.statuses.length || view.statuses.some((s) => STATUS[s]?.test(w)),
      cats: (w) =>
        !activeCats.length ||
        (catMode === "all" ? activeCats.every((c) => c !== NONE && hasCat(w, c)) : activeCats.some((c) => hasCat(w, c))),
    };
    const passes = (w, except) => Object.entries(tests).every(([k, t]) => k === except || t(w));
    // Conteos de cada opción con los demás filtros aplicados (como en solotodo).
    const count = (dim, has) => {
      const pool = watches.filter((w) => passes(w, dim));
      return (value) => pool.filter((w) => has(w, value)).length;
    };
    return {
      shown: sortWatches(watches.filter((w) => passes(w)), view.sort, view.dir),
      facets: {
        stores: count("stores", (w, p) => processorsOf(w).includes(p)),
        statuses: count("statuses", (w, s) => STATUS[s].test(w)),
        cats: count("cats", hasCat),
      },
    };
  }, [watches, view, activeCats, catMode, catsOf]);

  const stores = useMemo(
    () => [...new Set((watches ?? []).flatMap(processorsOf))].sort((a, b) => label(a).localeCompare(label(b))),
    [watches],
  );

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

  const groups =
    view.group === "store"
      ? groupBy(shown, (w) => [storeLabel(w)], MULTI)
      : view.group === "category"
        ? groupBy(shown, (w) => (catsOf(w).length ? catsOf(w).map((c) => c.name) : [NO_CATEGORY]), NO_CATEGORY)
        : [[null, shown]];
  const nFilters = (view.q.trim() ? 1 : 0) + view.stores.length + view.statuses.length + activeCats.length;
  const clearFilters = () => setView({ q: "", stores: [], statuses: [], cats: [], catMode: "any" });
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
  const replaceWatch = (next) => setWatches((list) => list.map((x) => (x.id === next.id ? next : x)));
  // Categorías nuevas de varios watches (asignación en masa): [{id, categories}].
  const patchCategories = (changes) => {
    const byId = new Map(changes.map((c) => [c.id, c.categories]));
    setWatches((list) => list.map((w) => (byId.has(w.id) ? { ...w, categories: byId.get(w.id) } : w)));
    cats.reload();
  };
  const filterByCategory = (id) => {
    setView({ cats: [id], catMode: "any" });
    if (selecting) setSelecting(false);
  };

  return (
    <>
      <div className="row-between page-head">
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

      <div className="catalog">
        {drawer && <div className="filters-backdrop" onClick={() => setDrawer(false)} />}
        <aside className={"filters" + (drawer ? " open" : "")} aria-label="Filtros">
          <div className="filters-head">
            <span className="small">
              <b>{shown.length}</b> {nFilters ? `de ${watches.length} ` : ""}producto{shown.length === 1 ? "" : "s"}
            </span>
            {nFilters > 0 && <button className="link small" onClick={clearFilters}>Borrar filtros</button>}
            <button className="icon-button filters-close" onClick={() => setDrawer(false)} aria-label="Cerrar filtros">✕</button>
          </div>
          <input type="search" placeholder="Buscar por nombre…" value={view.q} onChange={(e) => setView({ q: e.target.value })} aria-label="Buscar" />

          <CategoryFilter
            view={view}
            setView={setView}
            cats={cats}
            active={activeCats}
            mode={catMode}
            count={facets.cats}
            onDeleted={(id) => {
              setView({ cats: view.cats.filter((c) => c !== id) });
              setWatches((list) => list.map((w) => ({ ...w, categories: w.categories.filter((c) => c.id !== id) })));
            }}
          />

          <FilterSection id="stores" title="Tiendas" view={view} setView={setView} active={view.stores.length}>
            <StoreOptions stores={stores} info={storeInfo} value={view.stores} count={facets.stores} onChange={(v) => setView({ stores: v })} />
          </FilterSection>

          <FilterSection id="statuses" title="Estado" view={view} setView={setView} active={view.statuses.length}>
            <ul className="filter-options">
              {Object.entries(STATUS).map(([k, s]) => (
                <FilterOption key={k} checked={view.statuses.includes(k)} count={facets.statuses(k)} onChange={(on) => setView({ statuses: toggled(view.statuses, k, on) })}>
                  {s.label}
                </FilterOption>
              ))}
            </ul>
          </FilterSection>
        </aside>

        <div className="catalog-main">
          <div className="toolbar">
            <button className="secondary filters-toggle" onClick={() => setDrawer(true)}>
              Filtros{nFilters > 0 && ` (${nFilters})`}
            </button>
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
            <select value={view.group} onChange={(e) => setView({ group: e.target.value })} aria-label="Agrupar">
              {Object.entries(GROUPS).map(([k, g]) => <option key={k} value={k}>{g}</option>)}
            </select>
            <LayoutToggle value={view.layout} onChange={(layout) => setView({ layout })} />
          </div>

          {selecting && (
            <p className="muted small select-hint">
              Elige productos para cambiarles la categoría o, si son la misma cosa (por ejemplo, el mismo juego en dos tiendas), para seguirlos como uno solo.
            </p>
          )}

          {shown.length === 0 && (
            <p className="muted empty">
              Ningún producto coincide con los filtros. <button className="link" onClick={clearFilters}>Borrar filtros</button>
            </p>
          )}
          {groups.map(([group, items]) => (
            <section key={group ?? "all"}>
              {group && <h2 className="day-label">{group} · {items.length}</h2>}
              <ul className={"watch-list" + (view.layout === "grid" ? " grid" : "")}>
                {items.map((w) => (
                  <WatchCard
                    key={w.id}
                    w={w}
                    stores={storeInfo}
                    cats={cats}
                    catsOf={catsOf}
                    onCategory={filterByCategory}
                    selecting={selecting}
                    selected={selected.has(w.id)}
                    onToggle={() => toggle(w.id)}
                    onChange={replaceWatch}
                    onCategories={() => cats.reload()}
                    onRemove={() => {
                      setWatches(watches.filter((x) => x.id !== w.id));
                      cats.reload();
                    }}
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
                <SelectBar chosen={chosen} cats={cats} onMerge={() => setMerging(true)} onCategories={patchCategories} />
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const LAYOUTS = {
  list: {
    label: "Lista",
    icon: <path d="M3 4h10M3 8h10M3 12h10" />,
  },
  grid: {
    label: "Tarjetas",
    icon: <path d="M2.5 2.5h4.5v4.5h-4.5zM9 2.5h4.5v4.5h-4.5zM2.5 9h4.5v4.5h-4.5zM9 9h4.5v4.5h-4.5z" />,
  },
};

function LayoutToggle({ value, onChange }) {
  return (
    <div className="segmented layout-toggle" role="radiogroup" aria-label="Vista">
      {Object.entries(LAYOUTS).map(([k, l]) => (
        <button key={k} role="radio" aria-checked={value === k} className={value === k ? "on" : ""} onClick={() => onChange(k)} title={l.label} aria-label={l.label}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {l.icon}
          </svg>
        </button>
      ))}
    </div>
  );
}

// Sección plegable de la sidebar; se recuerda cuáles están plegadas.
function FilterSection({ id, title: heading, view, setView, active, extra, children }) {
  const collapsed = !!view.collapsed?.[id];
  return (
    <section className="filter-section">
      <div className="filter-title">
        <button
          className="filter-fold"
          onClick={() => setView({ collapsed: { ...view.collapsed, [id]: !collapsed } })}
          aria-expanded={!collapsed}
        >
          {heading}
          {active > 0 && <span className="count">{active}</span>}
          <span className="fold-icon" aria-hidden="true">{collapsed ? "▾" : "▴"}</span>
        </button>
        {extra}
      </div>
      {!collapsed && children}
    </section>
  );
}

function FilterOption({ checked, count, onChange, disabled, children }) {
  return (
    <li>
      <label className={"check filter-option" + (disabled ? " disabled" : "")}>
        <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span className="grow filter-label">{children}</span>
        <span className="muted small">{count}</span>
      </label>
    </li>
  );
}

function CategoryFilter({ view, setView, cats, active, mode, count, onDeleted }) {
  const [editing, setEditing] = useState(false);
  const list = cats.categories ?? [];
  const edit = (
    <button
      className={"icon-button filter-edit" + (editing ? " on" : "")}
      onClick={() => setEditing(!editing)}
      title={editing ? "Listo" : "Editar categorías"}
      aria-label={editing ? "Terminar de editar las categorías" : "Editar categorías"}
      aria-pressed={editing}
    >
      {editing ? "✓" : "✎"}
    </button>
  );
  const setMode = (all) => setView({ catMode: all ? "all" : "any", cats: all ? active.filter((c) => c !== NONE) : active });
  return (
    <FilterSection id="cats" title="Categorías" view={view} setView={setView} active={active.length} extra={edit}>
      {editing ? (
        <CategoryManager categories={list} setCategories={cats.setCategories} onDeleted={onDeleted} compact />
      ) : (
        <>
          {list.length === 0 && (
            <p className="muted small filter-hint">Crea categorías con ✎, o desde el menú ⋯ de un producto.</p>
          )}
          <ul className="filter-options">
            {list.map((c) => (
              <FilterOption key={c.id} checked={active.includes(c.id)} count={count(c.id)} onChange={(on) => setView({ cats: toggled(active, c.id, on) })}>
                <CategoryDot color={c.color} /> {c.name}
              </FilterOption>
            ))}
            {list.length > 0 && (
              <FilterOption
                checked={active.includes(NONE)}
                count={count(NONE)}
                disabled={mode === "all"}
                onChange={(on) => setView({ cats: toggled(active, NONE, on) })}
              >
                <span className="muted">{NO_CATEGORY}</span>
              </FilterOption>
            )}
          </ul>
          {list.length > 1 && (
            <label className="check toggle filter-mode small" title="Mostrar solo los productos que tienen todas las categorías elegidas">
              <input type="checkbox" checked={mode === "all"} onChange={(e) => setMode(e.target.checked)} />
              Coincidir todas
            </label>
          )}
        </>
      )}
    </FilterSection>
  );
}

function StoreOptions({ stores, info, value, count, onChange }) {
  const [all, setAll] = useState(false);
  // Las elegidas siempre a la vista, aunque estén más allá del corte.
  const shown = all || stores.length <= STORES_SHOWN ? stores : stores.filter((s, i) => i < STORES_SHOWN || value.includes(s));
  return (
    <>
      <ul className="filter-options">
        {shown.map((s) => (
          <FilterOption key={s} checked={value.includes(s)} count={count(s)} onChange={(on) => onChange(toggled(value, s, on))}>
            <StoreLogo name={s} url={info[s]?.logo_url} size={16} /> {label(s)}
          </FilterOption>
        ))}
      </ul>
      {stores.length > STORES_SHOWN && (
        <button className="link small" onClick={() => setAll(!all)}>
          {all ? "Ver menos" : `Ver todas (${stores.length})`}
        </button>
      )}
    </>
  );
}

// Por qué no se pueden juntar los elegidos (o null si se puede).
function mergeProblem(chosen) {
  if (chosen.length < 2) return "elige al menos dos.";
  const links = chosen.reduce((n, w) => n + w.items.length, 0);
  if (links > MAX_ITEMS) return `entre todos suman ${links} links; el máximo es ${MAX_ITEMS}.`;
  if (new Set(chosen.map((w) => w.currency)).size > 1) return "tienen monedas distintas.";
  return null;
}

function SelectBar({ chosen, cats, onMerge, onCategories }) {
  const problem = mergeProblem(chosen);
  const [cat, setCat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const apply = async (action) => {
    setBusy(true);
    setError("");
    try {
      const r = await api(`/api/categories/${cat}/watches`, { method: "POST", body: { watch_ids: chosen.map((w) => w.id), action } });
      onCategories(r.watches);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const can = chosen.length > 0 && cat !== "" && !busy;
  return (
    <div className="select-actions">
      <div className="row-between">
        <span className="small">
          {chosen.length === 0 ? "Ningún producto elegido" : `${chosen.length} elegido${chosen.length === 1 ? "" : "s"}`}
          {chosen.length > 1 && problem && <span className="muted"> · no se pueden juntar: {problem}</span>}
        </span>
        <button onClick={onMerge} disabled={problem !== null}>Juntar ({chosen.length})</button>
      </div>
      {(cats.categories ?? []).length > 0 && (
        <div className="bulk-cats">
          <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Categoría">
            <option value="">Categoría…</option>
            {cats.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="secondary" onClick={() => apply("add")} disabled={!can}>Agregar</button>
          <button className="secondary" onClick={() => apply("remove")} disabled={!can}>Quitar</button>
          {error && <span className="error small">{error}</span>}
        </div>
      )}
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

// Menú ⋯ de una tarjeta: renombrar, categorías y dejar de seguir sin entrar al producto.
function CardMenu({ w, cats, onRename, onRemove, onChange }) {
  const [open, setOpen] = useState(null); // null | "menu" | "cats"
  const close = useCallback(() => setOpen(null), []);
  const ref = useDismiss(open !== null, close);
  const [error, setError] = useState("");
  const pick = (fn) => () => {
    setOpen(null);
    fn();
  };
  const ids = w.categories.map((c) => c.id);
  const toggle = async (id, on) => {
    setError("");
    try {
      const next = on ? [...new Set([...ids, id])] : ids.filter((x) => x !== id);
      onChange(await api(`/api/watches/${w.id}/categories`, { method: "PUT", body: { ids: next } }));
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <div className="card-menu" ref={ref}>
      <button className="icon-button" onClick={() => setOpen(open ? null : "menu")} aria-label={`Opciones de ${title(w)}`} aria-expanded={open !== null} title="Opciones">⋯</button>
      {open === "menu" && (
        <div className="menu-popover" role="menu">
          <button role="menuitem" onClick={pick(onRename)}>Renombrar</button>
          <button role="menuitem" onClick={() => setOpen("cats")}>Categorías…</button>
          <button role="menuitem" className="danger-item" onClick={pick(onRemove)}>Dejar de seguir</button>
        </div>
      )}
      {open === "cats" && (
        <div className="menu-popover cat-popover">
          <CategoryPicker categories={cats.categories} value={ids} onToggle={toggle} onCreate={cats.create} />
          {error && <p className="error small">{error}</p>}
        </div>
      )}
    </div>
  );
}

function WatchCard({ w, stores, cats, catsOf, onCategory, selecting, selected, onToggle, onChange, onCategories, onRemove }) {
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
  const tags = catsOf(w);
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
        {tags.length > 0 && (
          <div className="card-cats">
            {tags.slice(0, MAX_CHIPS).map((c) => <CategoryChip key={c.id} category={c} onClick={() => onCategory(c.id)} />)}
            {tags.length > MAX_CHIPS && (
              <span className="muted small" title={tags.slice(MAX_CHIPS).map((c) => c.name).join(", ")}>+{tags.length - MAX_CHIPS}</span>
            )}
          </div>
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
        <CardMenu
          w={w}
          cats={cats}
          onRename={() => setNaming(w.name ?? "")}
          onRemove={remove}
          onChange={(next) => {
            onChange(next);
            onCategories();
          }}
        />
      )}
    </li>
  );
}
