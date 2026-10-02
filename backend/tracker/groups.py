"""Lectura de un Watch con varios links: la del item más barato con stock.

Cada item aporta su último `PricePoint` (las anomalías no generan uno, así que nunca
entran). Un item no cuenta si está `broken` o si su lectura tiene más de
`STALE_FACTOR` veces el intervalo de su tienda: un link que dejó de leerse no puede
quedar para siempre como "el mejor precio".
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker import rules
from tracker.models import PricePoint, Product, Watch
from tracker.processors import get_processor

STALE_FACTOR = 3


@dataclass
class ItemState:
    product: Product
    point: PricePoint | None
    counts: bool


def latest_point(db: DbSession, product_id: int) -> PricePoint | None:
    return db.scalar(
        select(PricePoint)
        .where(PricePoint.product_id == product_id)
        .order_by(PricePoint.checked_at.desc(), PricePoint.id.desc())
        .limit(1)
    )


def item_counts(product: Product, point: PricePoint | None, now: datetime) -> bool:
    if point is None or product.status == "broken":
        return False
    interval = get_processor(product.processor).check_interval
    return now - point.checked_at <= interval * STALE_FACTOR


def item_states(db: DbSession, watch: Watch, now: datetime) -> list[ItemState]:
    out = []
    for item in watch.items:
        point = latest_point(db, item.product_id)
        out.append(ItemState(item.product, point, item_counts(item.product, point, now)))
    return out


def best_item(states: list[ItemState]) -> ItemState | None:
    """El más barato con stock; sin stock en ninguno, el más barato (o el primero)."""
    counted = [s for s in states if s.counts]
    if not counted:
        return None
    in_stock = [s for s in counted if s.point.available and s.point.price is not None]
    if in_stock:
        return min(in_stock, key=lambda s: s.point.price)
    priced = [s for s in counted if s.point.price is not None]
    return min(priced, key=lambda s: s.point.price) if priced else counted[0]


def reading_of(state: ItemState | None) -> rules.Reading | None:
    if state is None:
        return None
    p = state.point
    return rules.Reading(p.price, p.list_price, p.available)


def group_reading(
    db: DbSession, watch: Watch, now: datetime
) -> tuple[rules.Reading | None, ItemState | None]:
    best = best_item(item_states(db, watch, now))
    return reading_of(best), best


def counted_ids(states: list[ItemState]) -> list[int]:
    return sorted(s.product.id for s in states if s.counts)


def remember(
    watch: Watch, reading: rules.Reading | None, best: ItemState | None, counted: list[int]
) -> None:
    """Guarda la lectura del grupo recién evaluada (el "antes" del próximo aviso)."""
    watch.last_price = reading.price if reading else None
    watch.last_available = reading.available if reading else None
    watch.last_best_product_id = best.product.id if best else None
    watch.counted_product_ids = counted


def recalibrate(db: DbSession, watch: Watch, now: datetime) -> None:
    """La lectura del grupo cambió por algo que no es un precio (se agregó, quitó o juntó
    un link, o uno dejó de contar): las reglas toman la lectura nueva sin avisar."""
    states = item_states(db, watch, now)
    best = best_item(states)
    reading = reading_of(best)
    if watch.price_at_start is None and reading is not None:
        watch.price_at_start = reading.price
    for rule in watch.rules:
        rule.state = rules.calibrate(
            rule.kind, rule.params, rule.state, reading, price_at_start=watch.price_at_start
        )
    remember(watch, reading, best, counted_ids(states))


def group_min_price(db: DbSession, watch: Watch, before: datetime | None = None) -> int | None:
    """Mínimo histórico del grupo (todo el historial de sus items)."""
    q = select(func.min(PricePoint.price)).where(
        PricePoint.product_id.in_([i.product_id for i in watch.items]),
        PricePoint.price.is_not(None),
    )
    if before is not None:
        q = q.where(PricePoint.checked_at < before)
    return db.scalar(q)


def display_name(watch: Watch) -> str:
    if watch.name:
        return watch.name
    return watch.items[0].product.title if watch.items else ""
