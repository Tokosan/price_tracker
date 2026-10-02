import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import RulesEditor, { DEFAULT_EDITOR, rulesFromEditor } from "../components/RulesEditor.jsx";
import { formatPrice, PROCESSOR_LABEL } from "../format.js";

// Máximo de links por producto (igual que el backend).
const MAX_ITEMS = 8;

export default function AddWatch() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [url, setUrl] = useState(params.get("url") || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [editor, setEditor] = useState(DEFAULT_EDITOR);
  const [unsupported, setUnsupported] = useState(false);
  // Otros links de la misma cosa: [{url, preview}] ya resueltos.
  const [extras, setExtras] = useState([]);
  const [mode, setMode] = useState(null); // null = el que corresponda por defecto
  const [name, setName] = useState("");

  const resolve = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setPreview(null);
    setExtras([]);
    setMode(null);
    setUnsupported(false);
    try {
      const data = await api("/api/resolve", { method: "POST", body: { url } });
      setPreview(data);
      const current = data.variants.find((v) => v.selected);
      setSelected(new Set([current ? current.url : data.product.url]));
    } catch (err) {
      if (err.status === 422 && err.detail?.code === "unsupported") setUnsupported(true);
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (u) => {
    const next = new Set(selected);
    next.has(u) ? next.delete(u) : next.add(u);
    setSelected(next);
  };

  const mainUrls = preview ? (preview.variants.length ? [...selected] : [preview.product.url]) : [];
  const total = mainUrls.length + extras.length;
  // Con links extra lo normal es seguirlos juntos; con solo variantes, por separado.
  const effectiveMode = total > 1 ? (mode ?? (extras.length ? "group" : "separate")) : "separate";
  const group = effectiveMode === "group";

  // Por qué no se puede crear (o null).
  const problem = (() => {
    if (!preview || mainUrls.length === 0) return preview?.variants.length ? "Elige al menos una opción." : null;
    if (!group) return null;
    if (total > MAX_ITEMS) return `Un producto puede tener como máximo ${MAX_ITEMS} links.`;
    const currencies = new Set([preview.product.currency, ...extras.map((x) => x.preview.product.currency)]);
    if (currencies.size > 1) return "Todos los links deben tener la misma moneda.";
    const taken = [preview, ...extras.map((x) => x.preview)].find((p) => p.watching_in);
    if (taken) return `«${taken.product.title}» ya está en tu producto «${taken.watching_in.name}»: quítalo o júntalos desde la lista.`;
    const takenVariant = preview.variants.find((v) => selected.has(v.url) && v.watching_in);
    if (takenVariant) return `«${takenVariant.label}» ya está en tu producto «${takenVariant.watching_in.name}».`;
    return null;
  })();

  const create = async () => {
    setError("");
    let rules;
    try {
      rules = rulesFromEditor(editor, preview.product.currency);
    } catch (err) {
      return setError(err.message);
    }
    setBusy(true);
    try {
      const urls = [...mainUrls, ...extras.map((x) => x.preview.product.url)];
      const body = { urls, rules, mode: effectiveMode, ...(group && name.trim() && { name: name.trim() }) };
      const created = await api("/api/watches", { method: "POST", body });
      navigate(created.length === 1 ? `/w/${created[0].id}` : "/");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const p = preview?.product;
  return (
    <>
      <h1>Agregar producto</h1>
      <form className="card url-form" onSubmit={resolve}>
        <input
          type="url"
          required
          placeholder="https://www.ikea.com/cl/es/p/…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button disabled={busy || !url}>{busy && !preview ? "Leyendo…" : "Buscar"}</button>
        {busy && !preview && (
          <p className="muted">Algunas tiendas (como Entrejuegos) pasan por una protección anti-bots: puede tardar hasta un minuto.</p>
        )}
      </form>
      <p className="muted small">
        ¿Qué tiendas funcionan? Mira las <Link to="/tiendas">tiendas soportadas</Link>.
      </p>

      {unsupported && (
        <div className="card">
          <h2>Esa tienda todavía no está soportada</h2>
          <p className="muted">
            Revisa la lista de <Link to="/tiendas">tiendas soportadas</Link> y pega el link de un producto de alguna de ellas.
          </p>
        </div>
      )}

      {p && (
        <div className="card">
          <div className="preview">
            {p.image_url && <img src={p.image_url} alt="" />}
            <div>
              <h2>{p.title}</h2>
              <div className="price">{formatPrice(p.current?.price, p.currency)}</div>
              {p.current?.list_price > p.current?.price && <div className="muted small">Precio normal {formatPrice(p.current.list_price, p.currency)}</div>}
              {p.current && !p.current.available && <span className="badge out">Sin stock</span>}
              {preview.watching_in && (
                <p className="muted small">
                  Ya lo sigues en <Link to={`/w/${preview.watching_in.id}`}>{preview.watching_in.name}</Link>.
                </p>
              )}
            </div>
          </div>

          {preview.variants.length > 1 && (
            <>
              <h3>{preview.variants_title || "Variantes"}</h3>
              <p className="muted small">{preview.variants_hint}</p>
              <ul className="variants">
                {preview.variants.map((v) => (
                  <li key={v.url}>
                    <label className="check">
                      <input type="checkbox" checked={selected.has(v.url)} onChange={() => toggle(v.url)} />
                      {v.label}
                      {v.selected && preview.processor !== "mercadolibre" && <span className="muted small"> (la del link)</span>}
                      {v.watching_in && <span className="muted small"> · ya la sigues en «{v.watching_in.name}»</span>}
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}

          <Extras extras={extras} setExtras={setExtras} currency={p.currency} />

          {total > 1 && (
            <div className="mode-choice">
              <label className="check">
                <input type="radio" name="mode" checked={group} onChange={() => setMode("group")} />
                <span>
                  <b>Un solo producto</b>
                  <span className="muted small"> · te avisamos por el más barato con stock entre los {total}</span>
                </span>
              </label>
              <label className="check">
                <input type="radio" name="mode" checked={!group} onChange={() => setMode("separate")} />
                <span>
                  <b>Productos separados</b>
                  <span className="muted small"> · {total} productos, cada uno con sus avisos</span>
                </span>
              </label>
              {group && (
                <label className="name-field">
                  <span>Nombre <span className="muted small">(opcional)</span></span>
                  <input value={name} maxLength={200} placeholder={p.title} onChange={(e) => setName(e.target.value)} />
                </label>
              )}
            </div>
          )}

          <h3>Avisarme cuando…</h3>
          <RulesEditor value={editor} onChange={setEditor} currency={p.currency} />
          {problem && <p className="warn small">{problem}</p>}
          {error && <p className="error">{error}</p>}
          <button onClick={create} disabled={busy || problem !== null}>
            {busy ? "Guardando…" : group || total === 1 ? "Seguir producto" : `Seguir ${total} productos`}
          </button>
        </div>
      )}
      {!p && error && <p className="error">{error}</p>}
    </>
  );
}

// Otros links de la misma cosa (otra tienda u otra publicación), cada uno con su vista previa.
function Extras({ extras, setExtras, currency }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api("/api/resolve", { method: "POST", body: { url } });
      if (extras.some((x) => x.preview.product.id === data.product.id)) throw new Error("Ese link ya está en la lista.");
      setExtras([...extras, { url, preview: data }]);
      setUrl("");
    } catch (err) {
      setError(err.status === 422 && err.detail?.code === "unsupported" ? "Esa tienda todavía no está soportada." : err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="extras">
      <h3>¿Está en otra tienda o publicación?</h3>
      <p className="muted small">Agrega sus links y lo sigues como un solo producto.</p>
      {extras.length > 0 && (
        <ul className="extra-list">
          {extras.map((x) => {
            const ep = x.preview.product;
            return (
              <li key={ep.id} className="extra">
                {ep.image_url ? <img src={ep.image_url} alt="" /> : <div className="img-ph" />}
                <div className="grow">
                  <div className="strong">{ep.title}</div>
                  <div className="muted small">
                    {PROCESSOR_LABEL[ep.processor] ?? ep.processor} · {formatPrice(ep.current?.price, ep.currency)}
                    {ep.current && !ep.current.available && " · sin stock"}
                    {ep.variant_label && ` · ${ep.variant_label}`}
                  </div>
                  {ep.currency !== currency && <div className="warn small">Otra moneda ({ep.currency}).</div>}
                  {x.preview.watching_in && (
                    <div className="warn small">
                      Ya está en <Link to={`/w/${x.preview.watching_in.id}`}>{x.preview.watching_in.name}</Link>.
                    </div>
                  )}
                </div>
                <button className="link danger-link" onClick={() => setExtras(extras.filter((y) => y !== x))}>Quitar</button>
              </li>
            );
          })}
        </ul>
      )}
      <form className="add-extra" onSubmit={add}>
        <input type="url" required placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="Otro link" />
        <button className="secondary" disabled={busy || !url}>{busy ? "Leyendo…" : "+ Agregar link"}</button>
      </form>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
