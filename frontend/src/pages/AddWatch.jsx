import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import RulesEditor, { DEFAULT_EDITOR, rulesFromEditor } from "../components/RulesEditor.jsx";
import { formatPrice } from "../format.js";

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
  const [note, setNote] = useState("");
  const [reported, setReported] = useState(false);

  const resolve = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setPreview(null);
    setUnsupported(false);
    setReported(false);
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
      const urls = preview.variants.length ? [...selected] : [preview.product.url];
      const created = await api("/api/watches", { method: "POST", body: { urls, rules } });
      navigate(created.length === 1 ? `/w/${created[0].id}` : "/");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const report = async () => {
    setBusy(true);
    try {
      await api("/api/site-requests", { method: "POST", body: { url, note } });
      setReported(true);
    } catch (err) {
      setError(err.message);
    } finally {
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
        ¿Qué tiendas funcionan? Mira los <Link to="/sitios">sitios soportados</Link>.
      </p>

      {unsupported && (
        <div className="card">
          <h2>Ese sitio todavía no está soportado</h2>
          {reported ? (
            <p>✅ Listo, el admin verá tu pedido.</p>
          ) : (
            <>
              <p>Puedes pedirle al admin que agregue un procesador para este sitio.</p>
              <label>Comentario (opcional)<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ej.: tienen buenos precios en juegos de mesa" /></label>
              <button onClick={report} disabled={busy}>Reportar sitio al admin</button>
            </>
          )}
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
              {preview.already_watching && <p className="muted small">Ya sigues este producto.</p>}
            </div>
          </div>

          {preview.variants.length > 1 && (
            <>
              <h3>Variantes</h3>
              <p className="muted small">Cada variante se sigue por separado. Marca las que quieras.</p>
              <ul className="variants">
                {preview.variants.map((v) => (
                  <li key={v.url}>
                    <label className="check">
                      <input type="checkbox" checked={selected.has(v.url)} onChange={() => toggle(v.url)} />
                      {v.label}
                      {v.selected && <span className="muted small"> (la del link)</span>}
                      {v.already_watching && <span className="muted small"> · ya la sigues</span>}
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h3>Avisarme cuando…</h3>
          <RulesEditor value={editor} onChange={setEditor} currency={p.currency} />
          {error && <p className="error">{error}</p>}
          <button onClick={create} disabled={busy || (preview.variants.length > 0 && selected.size === 0)}>
            {busy ? "Guardando…" : selected.size > 1 ? `Seguir ${selected.size} variantes` : "Seguir producto"}
          </button>
        </div>
      )}
      {!p && error && <p className="error">{error}</p>}
    </>
  );
}
