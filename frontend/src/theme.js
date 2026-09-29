// Tema de la UI: `theme` (system | light | dark) y `palette` (green | blue).
// Se guarda por usuario en el backend; localStorage es solo una caché para pintar
// el color correcto antes de que cargue /api/auth/me (y en el login).
import { api } from "./api.js";

const KEY = "tracker_theme";
const DEFAULTS = { theme: "system", palette: "green" };
const media = window.matchMedia("(prefers-color-scheme: dark)");
let current = { ...DEFAULTS };

export const effectiveMode = () =>
  current.theme === "system" ? (media.matches ? "dark" : "light") : current.theme;

export function applyTheme(prefs = {}) {
  current = { ...current, ...prefs };
  const root = document.documentElement;
  root.dataset.mode = effectiveMode();
  root.dataset.palette = current.palette;
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Sin storage (modo privado): el tema igual queda aplicado en esta pestaña.
  }
}

export function initTheme() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(KEY));
  } catch {
    saved = null;
  }
  applyTheme(saved && typeof saved === "object" ? saved : DEFAULTS);
  media.addEventListener("change", () => applyTheme());
}

// Aplica al instante y lo guarda en la cuenta.
export function saveTheme(patch) {
  applyTheme(patch);
  return api("/api/auth/preferences", { method: "PATCH", body: patch });
}
