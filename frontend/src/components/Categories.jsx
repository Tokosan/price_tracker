import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { CATEGORY_COLORS } from "../format.js";

const byName = (a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base" });

// Categorías del usuario. `create` la agrega a la lista y la devuelve.
export function useCategories() {
  const [categories, setCategories] = useState(null);
  const reload = useCallback(() => api("/api/categories").then(setCategories).catch(() => {}), []);
  useEffect(() => {
    reload();
  }, [reload]);
  const create = async (name) => {
    const cat = await api("/api/categories", { method: "POST", body: { name } });
    setCategories((list) => [...(list ?? []), cat].sort(byName));
    return cat;
  };
  return { categories, setCategories, reload, create };
}

// Cierra un popover al hacer clic fuera o con Escape.
export function useDismiss(open, onClose) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => ref.current && !ref.current.contains(e.target) && onClose();
    const esc = (e) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open, onClose]);
  return ref;
}

export function CategoryDot({ color }) {
  return <span className={`cat-dot cat-${color}`} aria-hidden="true" />;
}

// Chip con el color de la categoría. Con `onClick` es clicable (dentro de un link no
// navega); con `onRemove` lleva una ✕.
export function CategoryChip({ category, onClick, onRemove }) {
  const click = onClick && ((e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return (
    <span
      className={`cat-chip cat-${category.color}` + (onClick ? " clickable" : "")}
      onClick={click}
      onKeyDown={click && ((e) => (e.key === "Enter" || e.key === " ") && click(e))}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={onClick ? `Filtrar por «${category.name}»` : undefined}
    >
      {category.name}
      {onRemove && (
        <button type="button" className="cat-remove" onClick={onRemove} aria-label={`Quitar «${category.name}»`}>×</button>
      )}
    </span>
  );
}

// Lista de checkboxes con buscador; si lo escrito no existe, ofrece crearla.
export function CategoryPicker({ categories, value, onToggle, onCreate }) {
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const text = q.trim().replace(/\s+/g, " ");
  const shown = (categories ?? []).filter((c) => c.name.toLocaleLowerCase("es").includes(text.toLocaleLowerCase("es")));
  const exact = (categories ?? []).find((c) => c.name.toLocaleLowerCase("es") === text.toLocaleLowerCase("es"));

  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const cat = await onCreate(text);
      onToggle(cat.id, true);
      setQ("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const enter = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (exact) onToggle(exact.id, !value.includes(exact.id));
    else if (text) create();
  };

  return (
    <div className="cat-picker">
      <input autoFocus value={q} maxLength={40} placeholder="Buscar o crear…" onChange={(e) => setQ(e.target.value)} onKeyDown={enter} aria-label="Buscar o crear una categoría" />
      <ul>
        {shown.map((c) => (
          <li key={c.id}>
            <label className="check">
              <input type="checkbox" checked={value.includes(c.id)} onChange={(e) => onToggle(c.id, e.target.checked)} />
              <CategoryDot color={c.color} />
              <span className="grow">{c.name}</span>
            </label>
          </li>
        ))}
        {categories?.length === 0 && !text && <li className="muted small">Aún no tienes categorías: escribe un nombre para crear una.</li>}
      </ul>
      {text && !exact && (
        <button type="button" className="link cat-create" onClick={create} disabled={busy}>＋ Crear «{text}»</button>
      )}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

// Chips de las categorías elegidas + botón que abre el selector.
export function CategoryField({ categories, value, onChange, onCreate, disabled }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);
  const byId = useMemo(() => new Map((categories ?? []).map((c) => [c.id, c])), [categories]);
  const chosen = value.map((id) => byId.get(id)).filter(Boolean).sort(byName);
  const toggle = (id, on) => onChange(on ? [...new Set([...value, id])] : value.filter((x) => x !== id));
  return (
    <div className="cat-field" ref={ref}>
      {chosen.map((c) => (
        <CategoryChip key={c.id} category={c} onRemove={disabled ? undefined : () => toggle(c.id, false)} />
      ))}
      <button type="button" className="link cat-add" onClick={() => setOpen(!open)} disabled={disabled} aria-expanded={open}>
        {chosen.length ? "＋" : "＋ Categoría"}
      </button>
      {open && (
        <div className="menu-popover cat-popover">
          <CategoryPicker categories={categories} value={value} onToggle={toggle} onCreate={onCreate} />
        </div>
      )}
    </div>
  );
}

function ColorChoice({ value, onChange }) {
  return (
    <div className="color-choice" role="radiogroup" aria-label="Color">
      {Object.entries(CATEGORY_COLORS).map(([key, label]) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          className={`cat-swatch cat-${key}` + (value === key ? " on" : "")}
          onClick={() => onChange(key)}
          title={label}
          aria-label={label}
        />
      ))}
    </div>
  );
}

// Renombrar, cambiar el color, borrar y crear (en Ajustes y en la sidebar de Productos).
export function CategoryManager({ categories, setCategories, onDeleted, compact = false }) {
  const [error, setError] = useState("");
  const [coloring, setColoring] = useState(null);
  const [draft, setDraft] = useState("");

  const run = async (fn) => {
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    }
  };
  const patch = (cat, body) =>
    run(async () => {
      const next = await api(`/api/categories/${cat.id}`, { method: "PATCH", body });
      setCategories((list) => list.map((c) => (c.id === next.id ? next : c)).sort(byName));
    });
  const rename = (cat, name) => {
    const clean = name.trim().replace(/\s+/g, " ");
    if (clean && clean !== cat.name) patch(cat, { name: clean });
  };
  const remove = (cat) => {
    const msg = cat.count
      ? `¿Borrar la categoría «${cat.name}»? Se quitará de ${cat.count} producto${cat.count === 1 ? "" : "s"} (los productos no se borran).`
      : `¿Borrar la categoría «${cat.name}»?`;
    if (!confirm(msg)) return;
    run(async () => {
      await api(`/api/categories/${cat.id}`, { method: "DELETE" });
      setCategories((list) => list.filter((c) => c.id !== cat.id));
      onDeleted?.(cat.id);
    });
  };
  const create = (e) => {
    e.preventDefault();
    run(async () => {
      const cat = await api("/api/categories", { method: "POST", body: { name: draft } });
      setCategories((list) => [...list, cat].sort(byName));
      setDraft("");
    });
  };

  return (
    <div className={"cat-manager" + (compact ? " compact" : "")}>
      <ul>
        {(categories ?? []).map((c) => (
          <li key={c.id}>
            <div className="cat-row">
              <button type="button" className={`cat-swatch cat-${c.color}`} onClick={() => setColoring(coloring === c.id ? null : c.id)} title="Cambiar el color" aria-label={`Color de «${c.name}»`} aria-expanded={coloring === c.id} />
              <input
                key={c.name}
                defaultValue={c.name}
                maxLength={40}
                onBlur={(e) => rename(c, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.target.blur();
                  if (e.key === "Escape") {
                    e.target.value = c.name;
                    e.target.blur();
                  }
                }}
                aria-label={`Nombre de «${c.name}»`}
              />
              {!compact && <span className="muted small nowrap">{c.count} producto{c.count === 1 ? "" : "s"}</span>}
              <button type="button" className="icon-button danger-link" onClick={() => remove(c)} title="Borrar" aria-label={`Borrar «${c.name}»`}>✕</button>
            </div>
            {coloring === c.id && (
              <ColorChoice
                value={c.color}
                onChange={(color) => {
                  setColoring(null);
                  patch(c, { color });
                }}
              />
            )}
          </li>
        ))}
      </ul>
      <form className="cat-new" onSubmit={create}>
        <input value={draft} maxLength={40} placeholder="Nueva categoría" onChange={(e) => setDraft(e.target.value)} aria-label="Nueva categoría" />
        <button className="secondary" disabled={!draft.trim()}>Crear</button>
      </form>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
