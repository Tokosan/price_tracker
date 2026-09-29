import { amountToInput, parseAmount } from "../format.js";

// Una regla por tipo en la UI (el modelo admite varias, pero así es más simple).
export const RULE_KINDS = [
  { kind: "TARGET_PRICE", label: "Llega a un precio objetivo" },
  { kind: "DISCOUNT_PCT", label: "Tiene un descuento de al menos…" },
  { kind: "PRICE_DROP", label: "Baja de precio" },
  { kind: "PRICE_UP", label: "Sube de precio" },
  { kind: "PRICE_CHANGE", label: "El precio varía" },
  { kind: "OUT_OF_STOCK", label: "Se agota" },
  { kind: "BACK_IN_STOCK", label: "Vuelve a haber stock" },
];

export const RULE_LABEL = Object.fromEntries(RULE_KINDS.map((r) => [r.kind, r.label]));

// Estado del editor: { KIND: { on, id?, ...campos de texto } }
export function editorFromRules(rules, currency) {
  const st = {};
  for (const r of rules) {
    const p = r.params || {};
    const base = p.baseline;
    st[r.kind] = {
      on: r.enabled !== false,
      id: r.id,
      value: amountToInput(p.value, currency),
      pct: p.pct ?? p.min_pct ?? "",
      baseline: typeof base === "object" && base ? "fixed" : base || "watch_start",
      fixed: typeof base === "object" && base ? amountToInput(base.fixed, currency) : "",
    };
  }
  return st;
}

export const DEFAULT_EDITOR = { PRICE_DROP: { on: true, pct: "10" }, BACK_IN_STOCK: { on: true } };

// Editor → lista para la API. Lanza Error con un mensaje legible si algo falta.
export function rulesFromEditor(st, currency) {
  const out = [];
  for (const { kind } of RULE_KINDS) {
    const r = st[kind];
    if (!r?.on) continue;
    const base = { id: r.id, kind, enabled: true };
    if (kind === "TARGET_PRICE") {
      const value = parseAmount(r.value, currency);
      if (value === null) throw new Error("Indica el precio objetivo.");
      out.push({ ...base, params: { value } });
    } else if (kind === "DISCOUNT_PCT") {
      const pct = Number(r.pct);
      if (!(pct > 0 && pct < 100)) throw new Error("El descuento debe estar entre 1 y 99 %.");
      let baseline = r.baseline || "watch_start";
      if (baseline === "fixed") {
        const fixed = parseAmount(r.fixed, currency);
        if (!fixed) throw new Error("Indica el precio base del descuento.");
        baseline = { fixed };
      }
      out.push({ ...base, params: { pct, baseline } });
    } else if (kind === "PRICE_DROP" || kind === "PRICE_UP") {
      const min_pct = Number(r.pct);
      if (!(min_pct > 0)) throw new Error("Indica el % mínimo de cambio.");
      out.push({ ...base, params: { min_pct } });
    } else {
      out.push({ ...base, params: {} });
    }
  }
  return out;
}

export default function RulesEditor({ value, onChange, currency = "CLP" }) {
  const set = (kind, patch) => onChange({ ...value, [kind]: { ...value[kind], ...patch } });
  return (
    <div className="rules">
      {RULE_KINDS.map(({ kind, label }) => {
        const r = value[kind] || {};
        return (
          <div key={kind} className={"rule" + (r.on ? " on" : "")}>
            <label className="check">
              <input type="checkbox" checked={!!r.on} onChange={(e) => set(kind, { on: e.target.checked })} />
              {label}
            </label>
            {r.on && kind === "TARGET_PRICE" && (
              <div className="rule-params">
                <span>Avisar a</span>
                <input inputMode="decimal" placeholder="49.990" value={r.value ?? ""} onChange={(e) => set(kind, { value: e.target.value })} />
                <span>o menos</span>
              </div>
            )}
            {r.on && kind === "DISCOUNT_PCT" && (
              <div className="rule-params">
                <input inputMode="decimal" className="short" placeholder="20" value={r.pct ?? ""} onChange={(e) => set(kind, { pct: e.target.value })} />
                <span>% respecto de</span>
                <select value={r.baseline || "watch_start"} onChange={(e) => set(kind, { baseline: e.target.value })}>
                  <option value="watch_start">el precio al empezar a seguirlo</option>
                  <option value="list_price">el precio normal de la tienda (sin oferta)</option>
                  <option value="fixed">un precio que yo indico</option>
                </select>
                {r.baseline === "fixed" && (
                  <input inputMode="decimal" placeholder="59.990" value={r.fixed ?? ""} onChange={(e) => set(kind, { fixed: e.target.value })} />
                )}
              </div>
            )}
            {r.on && (kind === "PRICE_DROP" || kind === "PRICE_UP") && (
              <div className="rule-params">
                <span>al menos</span>
                <input inputMode="decimal" className="short" placeholder="10" value={r.pct ?? ""} onChange={(e) => set(kind, { pct: e.target.value })} />
                <span>% desde el último aviso</span>
              </div>
            )}
            {r.on && kind === "PRICE_CHANGE" && (
              <div className="rule-params">
                <span>Avisa cada vez que cambia respecto de la revisión anterior</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
