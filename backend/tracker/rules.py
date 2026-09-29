"""Motor de reglas puro: sin DB ni red, fácil de testear.

Cada regla recibe sus `params`, su `state` y la lectura nueva, y devuelve si se
disparó y su estado nuevo. El checker consolida las reglas disparadas de un
Watch en una sola notificación.

Semántica (ver plan.md, "Reglas"):

- TARGET_PRICE {value}: se dispara al llegar a `value` o menos. Queda desarmada
  hasta que el precio vuelve a subir por sobre `value` más la histéresis.
- DISCOUNT_PCT {pct, baseline}: igual, pero con el descuento respecto de la base:
  `watch_start` (precio al crear el Watch), `list_price` (precio "antes" de la
  tienda) o `{"fixed": N}`. Se re-arma cuando el descuento cae bajo `pct - 2`.
- PRICE_DROP {min_pct} / PRICE_UP {min_pct}: comparan contra el último precio
  **notificado** (no contra la lectura anterior), así una bajada lenta avisa una
  vez al acumular `min_pct` y una oscilación no genera ruido.
- OUT_OF_STOCK / BACK_IN_STOCK: cambios de disponibilidad.

Las reglas de precio no se evalúan si el producto no está disponible: no sirve
avisar que "llegó al objetivo" algo que no se puede comprar. El estado queda
intacto hasta la próxima lectura con stock.
"""

from dataclasses import dataclass, field
from typing import Any

KINDS = (
    "TARGET_PRICE",
    "DISCOUNT_PCT",
    "PRICE_DROP",
    "PRICE_UP",
    "PRICE_CHANGE",
    "OUT_OF_STOCK",
    "BACK_IN_STOCK",
)
PRICE_KINDS = {"TARGET_PRICE", "DISCOUNT_PCT", "PRICE_DROP", "PRICE_UP", "PRICE_CHANGE"}

# Histéresis: margen para re-armar reglas de umbral.
TARGET_REARM_PCT = 2.0  # el precio debe superar el objetivo en un 2 %
DISCOUNT_REARM_POINTS = 2.0  # el descuento debe caer 2 puntos bajo el umbral


@dataclass
class Reading:
    price: int | None
    list_price: int | None
    available: bool


@dataclass
class Fired:
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class RuleError(ValueError):
    """Parámetros inválidos para una regla."""


def validate_params(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Normaliza y valida los parámetros de una regla (lo usa la API)."""
    if kind not in KINDS:
        raise RuleError(f"regla desconocida: {kind}")
    if kind == "TARGET_PRICE":
        value = params.get("value")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RuleError("TARGET_PRICE necesita 'value' entero >= 0")
        return {"value": value}
    if kind == "DISCOUNT_PCT":
        pct = params.get("pct")
        if not isinstance(pct, int | float) or isinstance(pct, bool) or not 0 < pct < 100:
            raise RuleError("DISCOUNT_PCT necesita 'pct' entre 0 y 100")
        baseline = params.get("baseline", "watch_start")
        if isinstance(baseline, dict):
            fixed = baseline.get("fixed")
            if not isinstance(fixed, int) or isinstance(fixed, bool) or fixed <= 0:
                raise RuleError("la base fija necesita un entero > 0")
            baseline = {"fixed": fixed}
        elif baseline not in ("watch_start", "list_price"):
            raise RuleError("baseline debe ser watch_start, list_price o {fixed: N}")
        return {"pct": pct, "baseline": baseline}
    if kind in ("PRICE_DROP", "PRICE_UP"):
        min_pct = params.get("min_pct")
        if (
            not isinstance(min_pct, int | float)
            or isinstance(min_pct, bool)
            or not 0 < min_pct < 1000
        ):
            raise RuleError(f"{kind} necesita 'min_pct' > 0")
        return {"min_pct": min_pct}
    return {}


def initial_state(kind: str, current: Reading | None) -> dict[str, Any]:
    """Estado de una regla recién creada, a partir de la última lectura conocida."""
    if kind in ("TARGET_PRICE", "DISCOUNT_PCT"):
        return {"armed": True}
    if kind in ("PRICE_DROP", "PRICE_UP"):
        return {"last_notified_price": current.price if current else None}
    if kind == "PRICE_CHANGE":
        return {"last_price": current.price if current else None}
    return {"last_available": current.available if current else None}


def baseline_price(
    params: dict[str, Any], reading: Reading, price_at_start: int | None
) -> int | None:
    base = params.get("baseline", "watch_start")
    if isinstance(base, dict):
        return base.get("fixed")
    if base == "list_price":
        return reading.list_price
    return price_at_start


def evaluate(
    kind: str,
    params: dict[str, Any],
    state: dict[str, Any],
    reading: Reading,
    *,
    price_at_start: int | None = None,
) -> tuple[Fired | None, dict[str, Any]]:
    """Evalúa una regla. Nunca muta `state`: devuelve uno nuevo."""
    state = dict(state or {})
    price = reading.price

    if kind == "OUT_OF_STOCK":
        last = state.get("last_available")
        state["last_available"] = reading.available
        if last is True and not reading.available:
            return Fired(kind, "Se agotó"), state
        return None, state

    if kind == "BACK_IN_STOCK":
        last = state.get("last_available")
        state["last_available"] = reading.available
        if last is False and reading.available:
            return Fired(kind, "Volvió a estar disponible"), state
        return None, state

    # Reglas de precio: sin precio o sin stock, no se tocan.
    if price is None or not reading.available:
        return None, state

    if kind == "TARGET_PRICE":
        value = params["value"]
        armed = state.get("armed", True)
        if armed and price <= value:
            state["armed"] = False
            return Fired(kind, "Llegó al precio objetivo", {"target": value}), state
        if not armed and price > value * (1 + TARGET_REARM_PCT / 100):
            state["armed"] = True
        return None, state

    if kind == "DISCOUNT_PCT":
        base = baseline_price(params, reading, price_at_start)
        if not base or base <= 0:
            return None, state
        discount = (base - price) * 100 / base
        armed = state.get("armed", True)
        if armed and discount >= params["pct"]:
            state["armed"] = False
            return (
                Fired(
                    kind,
                    f"Descuento de {discount:.0f} % (umbral {params['pct']} %)",
                    {"discount_pct": round(discount, 1), "baseline": base},
                ),
                state,
            )
        if not armed and discount < params["pct"] - DISCOUNT_REARM_POINTS:
            state["armed"] = True
        return None, state

    if kind in ("PRICE_DROP", "PRICE_UP"):
        last = state.get("last_notified_price")
        if last is None:
            # Primera lectura con precio: es la referencia, no un cambio.
            state["last_notified_price"] = price
            return None, state
        if last <= 0:
            if kind == "PRICE_UP" and price > last:
                state["last_notified_price"] = price
                return Fired(kind, "Dejó de ser gratis", {"from": last}), state
            state["last_notified_price"] = price if kind == "PRICE_DROP" else last
            return None, state
        change = (price - last) * 100 / last
        if kind == "PRICE_DROP" and change <= -params["min_pct"]:
            state["last_notified_price"] = price
            return Fired(kind, f"Bajó {abs(change):.0f} %", {"from": last}), state
        if kind == "PRICE_UP" and change >= params["min_pct"]:
            state["last_notified_price"] = price
            return Fired(kind, f"Subió {change:.0f} %", {"from": last}), state
        return None, state

    if kind == "PRICE_CHANGE":
        last = state.get("last_price")
        state["last_price"] = price
        if last is None or price == last:
            return None, state
        if last <= 0:
            return Fired(kind, "El precio varió (dejó de ser gratis)", {"from": last}), state
        change = (price - last) * 100 / last
        pct = f"{change:+.1f}" if abs(change) < 1 else f"{change:+.0f}"
        return Fired(kind, f"El precio varió {pct} %", {"from": last}), state

    raise RuleError(f"regla desconocida: {kind}")


# Por defecto, una caída mayor a esto en una sola lectura se trata como anomalía, no
# como oferta. Cada procesador puede cambiarlo (`Processor.anomaly_drop_pct`).
ANOMALY_DROP_PCT = 80


def check_anomaly(
    reading: Reading,
    previous_price: int | None,
    max_drop_pct: int | None = ANOMALY_DROP_PCT,
    sold_out_without_price: bool = False,
) -> tuple[str, str] | None:
    """Devuelve (tipo, detalle) si la lectura parece un error de scraping.

    `max_drop_pct=None` desactiva el control de caídas. El precio nulo es anomalía,
    salvo que el procesador declare que sin precio y sin stock es un agotado real.
    """
    if reading.price is None:
        if sold_out_without_price and not reading.available:
            return None
        return "price_none", "El procesador no pudo leer el precio"
    if max_drop_pct is not None and previous_price and previous_price > 0:
        drop = (previous_price - reading.price) * 100 / previous_price
        if drop > max_drop_pct:
            return (
                "big_drop",
                f"Caída de {drop:.0f} % en una lectura ({previous_price} → {reading.price})",
            )
    return None
