import { useCallback, useEffect, useState } from "react";
import { api } from "../../api.js";

// Carga uno o más endpoints del admin y permite recargarlos tras una acción.
export function useAdminData(paths) {
  const key = paths.join("|");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setData(await Promise.all(key.split("|").map((p) => api(p))));
    } catch (e) {
      setError(e.message);
    }
  }, [key]);
  useEffect(() => {
    load();
  }, [load]);
  // Ejecuta una acción, muestra su error si falla y recarga.
  const run = async (fn) => {
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    }
  };
  return { data, error, setError, run, reload: load };
}
