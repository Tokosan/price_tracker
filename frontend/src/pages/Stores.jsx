import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import StoreLogo, { loadStores } from "../components/StoreLogo.jsx";
import { relative } from "../format.js";

const STATUS = {
  ok: { label: "Funcionando", cls: "ok" },
  problems: { label: "Con problemas", cls: "problems" },
  unknown: { label: "Sin lecturas aún", cls: "unknown" },
};

function every(hours) {
  return hours % 24 === 0 && hours >= 24 ? `cada ${hours / 24} d` : `cada ${hours} h`;
}

const Check = ({ on }) => (on ? <span className="yes" aria-label="sí">✓</span> : <span className="muted" aria-label="no">—</span>);

export default function Stores() {
  const [stores, setStores] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    loadStores().then(setStores).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!stores) return <p className="muted">Cargando…</p>;

  return (
    <>
      <h1>Tiendas soportadas</h1>
      <p className="muted">
        Pega el link de un producto de cualquiera de estas tiendas en <Link to="/agregar">Agregar</Link>.
      </p>
      <div className="card table-card">
        <table className="stores">
          <thead>
            <tr>
              <th>Tienda</th>
              <th>Estado</th>
              <th className="hide-sm">Revisión</th>
              <th className="hide-sm">Precio normal</th>
              <th className="hide-sm">Variantes</th>
              <th className="num hide-sm">Tus productos</th>
              <th aria-label="Detalle" />
            </tr>
          </thead>
          <tbody>
            {stores.map((s) => {
              const st = STATUS[s.status] ?? STATUS.unknown;
              const isOpen = open === s.name;
              const toggle = () => setOpen(isOpen ? null : s.name);
              return (
                <Fragment key={s.name}>
                  <tr className={"store-row" + (isOpen ? " open" : "")} onClick={toggle}>
                    <td>
                      <div className="store-name">
                        <StoreLogo name={s.name} url={s.logo_url} label={s.label} />
                        <div>
                          <div className="strong">
                            {s.label}
                            {s.slow && <span className="badge warn-badge" title="Tiene protección anti-bots: la primera lectura puede tardar hasta un minuto.">Lenta</span>}
                          </div>
                          <a href={s.home_url} target="_blank" rel="noreferrer" className="muted small" onClick={(e) => e.stopPropagation()}>
                            {s.domain.replace(/^www\./, "")}
                          </a>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`store-status ${st.cls}`} title={s.last_ok_at ? `Última lectura correcta ${relative(s.last_ok_at)}` : undefined}>
                        {st.label}
                      </span>
                    </td>
                    <td className="nowrap hide-sm">{every(s.check_interval_hours)}</td>
                    <td className="hide-sm"><Check on={s.supports_list_price} /></td>
                    <td className="hide-sm"><Check on={s.supports_variants} /></td>
                    <td className="num hide-sm">{s.my_watches}</td>
                    <td className="num">
                      <button className="icon-button chevron" aria-expanded={isOpen} aria-label={`Detalle de ${s.label}`} onClick={(e) => { e.stopPropagation(); toggle(); }}>
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="store-detail">
                      <td colSpan={7}>
                        {s.notes && <p>{s.notes}</p>}
                        <p className="muted small">
                          Revisión {every(s.check_interval_hours)} · plataforma: {s.platform || "—"} · precio normal (antes de la oferta): {s.supports_list_price ? "sí" : "no"} · variantes: {s.supports_variants ? "sí" : "no"} · tus productos: {s.my_watches}
                        </p>
                        {s.example_url && (
                          <Link className="button secondary" to={`/agregar?url=${encodeURIComponent(s.example_url)}`}>
                            Probar con un ejemplo
                          </Link>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
