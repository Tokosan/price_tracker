// Montos enteros en unidad mínima → texto. Mismo criterio que el backend.
const EXPONENT = { CLP: 0, JPY: 0, KRW: 0, PYG: 0, ISK: 0, VND: 0 };
const SYMBOL = { CLP: "$", USD: "US$", EUR: "€" };

export const exponent = (cur) => EXPONENT[(cur || "CLP").toUpperCase()] ?? 2;

export function formatPrice(amount, currency = "CLP") {
  if (amount === null || amount === undefined) return "sin precio";
  const exp = exponent(currency);
  const value = amount / 10 ** exp;
  const text = value.toLocaleString("es-CL", {
    minimumFractionDigits: exp,
    maximumFractionDigits: exp,
  });
  return (SYMBOL[currency] ?? currency + " ") + text;
}

// "59.990" (lo que escribe la persona) → entero en unidad mínima.
export function parseAmount(text, currency = "CLP") {
  const exp = exponent(currency);
  const clean = String(text).trim().replace(/\./g, "").replace(",", ".");
  const n = Number(clean);
  if (!clean || Number.isNaN(n) || n < 0) return null;
  return Math.round(n * 10 ** exp);
}

export function amountToInput(amount, currency = "CLP") {
  if (amount === null || amount === undefined) return "";
  const exp = exponent(currency);
  return exp ? (amount / 10 ** exp).toFixed(exp).replace(".", ",") : String(amount);
}

export function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CL", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTime(iso) {
  return new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
}

// "Hoy", "Ayer" o "28 sept" (con año si no es el actual).
export function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const days = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 86400000);
  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  return d.toLocaleDateString("es-CL", {
    day: "numeric",
    month: "short",
    ...(d.getFullYear() !== today.getFullYear() && { year: "numeric" }),
  });
}

export function relative(iso) {
  if (!iso) return "nunca";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const abs = Math.abs(diff);
  const fut = diff < 0;
  const unit =
    abs < 60 ? "unos segundos" : abs < 3600 ? `${Math.round(abs / 60)} min` : abs < 86400 ? `${Math.round(abs / 3600)} h` : `${Math.round(abs / 86400)} d`;
  return fut ? `en ${unit}` : `hace ${unit}`;
}

export const PROCESSOR_LABEL = { steam: "Steam", ikea: "IKEA", entrejuegos: "Entrejuegos", dementegames: "DementeGames", lafortaleza: "La Fortaleza", mercadolibre: "MercadoLibre", lider: "Lider", jumbo: "Jumbo", pcfactory: "PC Factory", falabella: "Falabella", hites: "Hites", solotodo: "Solotodo" };

// Color de la n-ésima serie (link) de un gráfico: orden fijo, hasta 8 (el máximo de links).
export const seriesColor = (n) => `var(--series-${(n % 8) + 1})`;
