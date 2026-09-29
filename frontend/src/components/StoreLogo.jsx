import { useEffect, useState } from "react";
import { api } from "../api.js";
import { PROCESSOR_LABEL } from "../format.js";

// Tiendas (/api/processors) compartidas entre páginas: se piden una vez por carga.
let storesPromise = null;
export function loadStores({ refresh = false } = {}) {
  if (refresh || !storesPromise) {
    storesPromise = api("/api/processors").catch((e) => {
      storesPromise = null;
      throw e;
    });
  }
  return storesPromise;
}

// {procesador: tienda} para mostrar logos en listas.
export function useStores() {
  const [stores, setStores] = useState({});
  useEffect(() => {
    loadStores()
      .then((list) => setStores(Object.fromEntries(list.map((s) => [s.name, s]))))
      .catch(() => {});
  }, []);
  return stores;
}

// Color estable por tienda para el respaldo con la inicial.
function hue(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

// Logo de la tienda sobre fondo blanco (los PNG suelen asumirlo); sin logo, la inicial.
export default function StoreLogo({ name, url, label, size = 34 }) {
  const [broken, setBroken] = useState(false);
  const text = label ?? PROCESSOR_LABEL[name] ?? name;
  const style = { "--size": `${size}px`, "--h": hue(name) };
  if (url && !broken) {
    return <img className="store-logo" src={url} alt="" style={style} onError={() => setBroken(true)} />;
  }
  return <span className="store-logo letter" style={style} aria-hidden="true">{text.charAt(0)}</span>;
}
