"""Revisión de un producto: fetch → validación → PricePoint → reglas → notificación."""

import asyncio
import logging
import random
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from tracker import groups, rules
from tracker.config import settings
from tracker.db import SessionLocal, utcnow
from tracker.models import Anomaly, Notification, PricePoint, Product, User, Watch, WatchItem
from tracker.money import format_change, format_price
from tracker.notifications.notifier import channels_for_watch, esc, notify_admins, send_to_channels
from tracker.processors import FetchError, ProductRef, ScrapeResult, get_processor

log = logging.getLogger("tracker.checker")

BROKEN_AFTER = 5
MAX_BACKOFF = timedelta(hours=24)

# --- Rate limit por dominio ---------------------------------------------------
_domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_domain_last: dict[str, float] = {}
_in_flight: set[int] = set()


@asynccontextmanager
async def domain_slot(domain: str):
    """Una petición a la vez por dominio y al menos N segundos entre ellas."""
    async with _domain_locks[domain]:
        wait = _domain_last.get(domain, 0) + settings.domain_min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            yield
        finally:
            _domain_last[domain] = time.monotonic()


def is_in_flight(product_id: int) -> bool:
    return product_id in _in_flight


# --- Planificación --------------------------------------------------------------
def next_check(interval: timedelta, now: datetime) -> datetime:
    """Intervalo fijo del procesador con jitter de ±20 %."""
    return now + interval * random.uniform(0.8, 1.2)


def backoff_delay(fail_count: int) -> timedelta:
    """1 h, 2 h, 4 h… con tope de 24 h."""
    return min(timedelta(hours=2 ** max(fail_count - 1, 0)), MAX_BACKOFF)


@dataclass
class CheckOutcome:
    ok: bool
    price: int | None = None
    available: bool | None = None
    anomaly: str | None = None
    error: str | None = None
    notifications: list[int] = field(default_factory=list)


async def check_product(product_id: int) -> CheckOutcome:
    """Revisa un producto. Seguro de llamar desde el scheduler o desde la API."""
    if product_id in _in_flight:
        return CheckOutcome(ok=False, error="ya se está revisando")
    _in_flight.add(product_id)
    try:
        with SessionLocal() as db:
            product = db.get(Product, product_id)
            if product is None:
                return CheckOutcome(ok=False, error="no existe")
            proc = get_processor(product.processor)
            ref = ProductRef(product.external_id, product.canonical_url, product.variant_id)
        try:
            async with domain_slot(proc.domain()):
                result = await proc.fetch(ref)
        except FetchError as exc:
            return await record_failure(product_id, str(exc))
        except Exception as exc:  # un bug del parser no debe tumbar el scheduler
            log.exception("error inesperado revisando producto %s", product_id)
            return await record_failure(product_id, f"error inesperado: {exc!r}")
        with SessionLocal() as db:
            product = db.get(Product, product_id)
            assert product is not None
            return await apply_result(db, product, result)
    finally:
        _in_flight.discard(product_id)


async def record_failure(product_id: int, error: str) -> CheckOutcome:
    now = utcnow()
    became_broken = False
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if product is None:
            return CheckOutcome(ok=False, error=error)
        product.fail_count += 1
        product.last_error = error[:1000]
        product.last_checked_at = now
        product.next_check_at = now + backoff_delay(product.fail_count)
        if product.fail_count >= BROKEN_AFTER and product.status != "broken":
            product.status = "broken"
            became_broken = True
        db.commit()
        log.warning("producto %s falló (%s seguidos): %s", product_id, product.fail_count, error)
        if became_broken:
            await notify_admins(
                db,
                f"⚠️ <b>Producto broken</b> tras {product.fail_count} fallos seguidos\n"
                f"{esc(product.title)} ({product.processor})\n{esc(error)[:300]}",
            )
    return CheckOutcome(ok=False, error=error)


def _reading(result: ScrapeResult) -> rules.Reading:
    return rules.Reading(result.price, result.list_price, result.available)


def last_good_price(db: DbSession, product_id: int) -> int | None:
    return db.scalar(
        select(PricePoint.price)
        .where(PricePoint.product_id == product_id, PricePoint.price.is_not(None))
        .order_by(PricePoint.checked_at.desc(), PricePoint.id.desc())
        .limit(1)
    )


async def apply_result(
    db: DbSession, product: Product, result: ScrapeResult, now: datetime | None = None
) -> CheckOutcome:
    """Aplica una lectura exitosa. Separado del fetch para poder testearlo sin red."""
    now = now or utcnow()
    proc = get_processor(product.processor)
    if result.title:
        product.title = result.title[:500]
    if result.image_url:
        product.image_url = result.image_url
    product.currency = result.currency or product.currency
    product.last_checked_at = now
    product.next_check_at = next_check(proc.check_interval, now)

    reading = _reading(result)
    previous = last_good_price(db, product.id)
    anomaly = rules.check_anomaly(
        reading, previous, proc.anomaly_drop_pct, proc.sold_out_without_price
    )
    if anomaly:
        # Nunca se alerta con una lectura sospechosa: se registra y se corta aquí.
        kind, detail = anomaly
        db.add(Anomaly(product_id=product.id, kind=kind, detail=detail, created_at=now))
        db.commit()
        log.warning("anomalía en producto %s: %s", product.id, detail)
        return CheckOutcome(ok=False, price=result.price, available=result.available, anomaly=kind)

    was_broken = product.status == "broken"
    product.fail_count = 0
    product.last_error = None
    product.status = "ok"
    db.add(
        PricePoint(
            product_id=product.id,
            price=result.price,
            list_price=result.list_price,
            available=result.available,
            checked_at=now,
        )
    )
    db.flush()
    if was_broken:
        log.info("producto %s se recuperó", product.id)

    pending: list[tuple[Notification, Watch, str]] = []
    watches = db.scalars(
        select(Watch)
        .join(WatchItem, WatchItem.watch_id == Watch.id)
        .join(User, User.id == Watch.user_id)
        .where(WatchItem.product_id == product.id, Watch.active.is_(True), User.active.is_(True))
    ).all()
    for watch in watches:
        notif, text = evaluate_watch(db, watch, now)
        if notif is not None:
            db.add(notif)
            pending.append((notif, watch, text))
    db.commit()

    # El envío va después del commit: si Telegram falla, el historial in-app queda igual.
    for notif, watch, text in pending:
        notif.delivery = await send_to_channels(channels_for_watch(db, watch), text)
    if pending:
        db.commit()
    return CheckOutcome(
        ok=True,
        price=result.price,
        available=result.available,
        notifications=[n.id for n, _, _ in pending],
    )


def evaluate_watch(db: DbSession, watch: Watch, now: datetime) -> tuple[Notification | None, str]:
    """Evalúa las reglas de un Watch contra la lectura de su grupo.

    Se llama cada vez que cualquiera de sus items recibe una lectura válida. Devuelve
    la notificación consolidada (sin agregarla a la sesión) y su texto, o (None, "").
    """
    states = groups.item_states(db, watch, now)
    counted = groups.counted_ids(states)
    previous_counted = watch.counted_product_ids
    if previous_counted and set(previous_counted) != set(counted):
        # Un item dejó de contar (broken, sin lecturas) o volvió: el cambio de la lectura
        # del grupo es un efecto de eso, no del precio. Nunca se avisa por un error.
        groups.recalibrate(db, watch, now)
        return None, ""
    best = groups.best_item(states)
    reading = groups.reading_of(best)
    if reading is None or best is None:
        watch.counted_product_ids = counted
        return None, ""
    if watch.price_at_start is None:
        watch.price_at_start = reading.price
    previous_price, previous_best = watch.last_price, watch.last_best_product_id
    fired: list[rules.Fired] = []
    for rule in watch.rules:
        if not rule.enabled:
            continue
        hit, new_state = rules.evaluate(
            rule.kind, rule.params, rule.state, reading, price_at_start=watch.price_at_start
        )
        rule.state = new_state
        if hit:
            fired.append(hit)
    groups.remember(watch, reading, best, counted)
    if not fired:
        return None, ""

    winner = best.product
    multi = len(watch.items) > 1
    prior_min = groups.group_min_price(db, watch, before=now)
    historic_min = reading.price is not None and prior_min is not None and reading.price < prior_min
    previous_store = None
    if multi and previous_best is not None and previous_best != winner.id:
        prev = db.get(Product, previous_best)
        previous_store = get_processor(prev.processor).label if prev else None
    title = groups.display_name(watch)
    text = build_message(
        title,
        winner,
        reading,
        fired,
        historic_min,
        previous_price,
        store=get_processor(winner.processor).label if multi else None,
        previous_store=previous_store,
        price_at_start=watch.price_at_start,
    )
    notif = Notification(
        watch_id=watch.id,
        payload={
            "title": title,
            "url": winner.canonical_url,
            "product_id": winner.id,
            "processor": winner.processor,
            "item_title": winner.title,
            "price": reading.price,
            "list_price": reading.list_price,
            # Lectura anterior del grupo: es el "antes" del aviso (list_price es el
            # precio normal de la tienda, no el anterior).
            "previous_price": previous_price,
            "price_at_start": watch.price_at_start,
            "currency": winner.currency,
            "available": reading.available,
            "historic_min": historic_min,
            "fired": [{"kind": f.kind, "message": f.message, **f.data} for f in fired],
        },
        sent_at=now,
        delivery={},
    )
    return notif, text


def build_message(
    title: str,
    product: Product,
    reading: rules.Reading,
    fired: list[rules.Fired],
    historic_min: bool,
    previous_price: int | None = None,
    *,
    store: str | None = None,
    previous_store: str | None = None,
    price_at_start: int | None = None,
) -> str:
    """Texto del aviso. `store` solo va en Watches con varios links (dónde está el precio)."""
    cur = product.currency
    lines = [f"<b>{esc(title)}</b>"]
    price_line = format_price(reading.price, cur)
    if store:
        price_line += f" en {esc(store)}"
    if not reading.available:
        price_line += " · sin stock"
    lines.append(price_line)
    # Variación en plata y en %: contra la lectura anterior y contra el inicio del
    # seguimiento (siempre las dos, aunque coincidan o no haya cambio).
    if reading.price is not None:
        if previous_price is not None:
            before = format_price(previous_price, cur)
            if previous_store:
                before += f" en {esc(previous_store)}"
            change = esc(format_change(reading.price, previous_price, cur))
            lines.append(f"vs. anterior ({before}): {change}")
        if price_at_start is not None:
            change = esc(format_change(reading.price, price_at_start, cur))
            lines.append(f"vs. inicio ({format_price(price_at_start, cur)}): {change}")
    if reading.list_price and reading.price is not None and reading.list_price > reading.price:
        lines.append(f"Precio normal {format_price(reading.list_price, cur)}")
    for f in fired:
        extra = ""
        if "target" in f.data:
            extra = f" (objetivo {format_price(f.data['target'], cur)})"
        elif "from" in f.data and f.data["from"] not in (previous_price, price_at_start):
            # PRICE_DROP / PRICE_UP comparan contra el último aviso, no contra la
            # lectura anterior: ese "desde" sí aporta (salvo que repita una de las bases).
            extra = f" (desde {format_price(f.data['from'], cur)})"
        lines.append(f"• {esc(f.message)}{extra}")
    if historic_min:
        lines.append("🏷️ Mínimo histórico")
    lines.append(product.canonical_url)
    return "\n".join(lines)
