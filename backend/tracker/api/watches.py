"""Watches del usuario: agregar por link, reglas, historial y "Revisar ahora".

Privacidad: toda consulta filtra por `Watch.user_id == user.id`.
"""

from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as DbSession

from tracker import groups, logos, rules
from tracker.api.deps import current_user
from tracker.checker import apply_result, check_product, domain_slot, is_in_flight
from tracker.config import settings
from tracker.db import get_db, utcnow
from tracker.groups import latest_point
from tracker.models import (
    AlertRule,
    Category,
    Channel,
    Notification,
    PricePoint,
    Product,
    User,
    Watch,
    WatchChannel,
    WatchItem,
)
from tracker.processors import FetchError, Processor, ProductRef, find_processor, get_processor

router = APIRouter(prefix="/api", tags=["watches"])

# Más líneas que esto no se distinguen en el gráfico.
MAX_ITEMS = 8


def iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# --- Serialización -----------------------------------------------------------------
def product_out(db: DbSession, product: Product, point: PricePoint | None = None) -> dict:
    point = point or latest_point(db, product.id)
    min_price = db.scalar(
        select(func.min(PricePoint.price)).where(
            PricePoint.product_id == product.id, PricePoint.price.is_not(None)
        )
    )
    return {
        "id": product.id,
        "processor": product.processor,
        "title": product.title,
        # Qué se sigue cuando no es obvio (p. ej. qué oferta de un catálogo de MercadoLibre).
        "variant_label": get_processor(product.processor).variant_label(
            product.external_id, product.variant_id
        ),
        "image_url": product.image_url,
        "url": product.canonical_url,
        "currency": product.currency,
        "status": product.status,
        "last_checked_at": iso(product.last_checked_at),
        "next_check_at": iso(product.next_check_at),
        "manual_check_available_at": iso(cooldown_until(product)),
        "current": (
            {
                "price": point.price,
                "list_price": point.list_price,
                "available": point.available,
                "checked_at": iso(point.checked_at),
            }
            if point
            else None
        ),
        "min_price": min_price,
    }


def cooldown_until(product: Product) -> datetime | None:
    """Hasta cuándo no se puede "Revisar ahora" este producto (None = ya se puede)."""
    if product.last_manual_check_at is None:
        return None
    until = product.last_manual_check_at + timedelta(minutes=settings.manual_check_cooldown_min)
    return until if until > utcnow() else None


def rule_out(rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "kind": rule.kind,
        "params": rule.params,
        "enabled": rule.enabled,
        "armed": rule.state.get("armed"),
    }


def watch_channels(db: DbSession, watch: Watch) -> dict[str, bool]:
    """{kind: habilitado para este Watch} de los canales que el usuario tiene."""
    out: dict[str, bool] = {}
    for ch in db.scalars(select(Channel).where(Channel.user_id == watch.user_id)):
        override = db.get(WatchChannel, (watch.id, ch.id))
        out[ch.kind] = override.enabled if override else True
    return out


def watch_out(db: DbSession, watch: Watch) -> dict:
    channels = watch_channels(db, watch)
    states = groups.item_states(db, watch, utcnow())
    best = groups.best_item(states)
    items = [
        {
            **product_out(db, s.product, s.point),
            "counts": s.counts,
            "best": best is not None and s.product.id == best.product.id,
        }
        for s in states
    ]
    # "Revisar ahora" del Watch: disponible si algún item se puede revisar.
    waits = [cooldown_until(s.product) for s in states]
    check_at = min(waits) if waits and all(waits) else None
    return {
        "id": watch.id,
        "name": watch.name,
        "display_name": groups.display_name(watch),
        "active": watch.active,
        "created_at": iso(watch.created_at),
        "price_at_start": watch.price_at_start,
        "currency": watch_currency(watch),
        "best": (
            {
                "product_id": best.product.id,
                "processor": best.product.processor,
                "price": best.point.price,
                "list_price": best.point.list_price,
                "available": best.point.available,
                "checked_at": iso(best.point.checked_at),
            }
            if best
            else None
        ),
        "min_price": groups.group_min_price(db, watch),
        "manual_check_available_at": iso(check_at),
        "items": items,
        # Compatibilidad con la UI de un solo link: el primer item.
        "product": items[0] if items else None,
        "rules": [rule_out(r) for r in watch.rules],
        "categories": categories_of(watch),
        "channels": channels,
        # Compatibilidad con la UI de la v0.
        "telegram_enabled": channels.get("telegram"),
    }


def categories_of(watch: Watch) -> list[dict]:
    return [{"id": c.id, "name": c.name, "color": c.color} for c in watch.categories]


def watch_currency(watch: Watch) -> str:
    return watch.items[0].product.currency if watch.items else "CLP"


def get_own_watch(db: DbSession, user: User, watch_id: int) -> Watch:
    watch = db.get(Watch, watch_id)
    # 404 también si es de otro usuario: no se revela que existe.
    if watch is None or watch.user_id != user.id:
        raise HTTPException(404, "no existe")
    return watch


def own_category(db: DbSession, user: User, category_id: int) -> Category:
    category = db.get(Category, category_id)
    # 404 también si es de otro usuario, igual que con los Watches.
    if category is None or category.user_id != user.id:
        raise HTTPException(404, "esa categoría no existe")
    return category


def own_categories(db: DbSession, user: User, ids: list[int]) -> list[Category]:
    return [own_category(db, user, i) for i in dict.fromkeys(ids)]


def own_item(db: DbSession, user: User, product_id: int) -> WatchItem | None:
    """El item del usuario con ese producto (un producto va en un solo Watch)."""
    return db.scalar(
        select(WatchItem).where(WatchItem.user_id == user.id, WatchItem.product_id == product_id)
    )


# --- Resolver un link ------------------------------------------------------------------
class ResolveIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


def _processor_or_422(url: str) -> Processor:
    proc = find_processor(url.strip())
    if proc is None:
        raise HTTPException(
            422,
            {
                "code": "unsupported",
                "message": "Esa tienda todavía no está soportada.",
            },
        )
    return proc


def get_or_create_product(db: DbSession, proc: Processor, ref: ProductRef) -> Product:
    product = db.scalar(
        select(Product).where(
            Product.processor == proc.name,
            Product.external_id == ref.external_id,
            Product.variant_id == ref.variant_id,
        )
    )
    if product is None:
        product = Product(
            processor=proc.name,
            external_id=ref.external_id,
            variant_id=ref.variant_id,
            canonical_url=ref.canonical_url,
            next_check_at=utcnow(),
        )
        db.add(product)
        db.flush()
    return product


async def _read_if_new(db: DbSession, product: Product) -> None:
    """Un producto que nunca se leyó (p. ej. una variante hermana) se lee ahora."""
    if latest_point(db, product.id) is None:
        db.commit()
        await check_product(product.id)
        db.expire_all()


@router.post("/resolve")
async def resolve(
    body: ResolveIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    """Pide la página una vez: devuelve la vista previa y las variantes hermanas."""
    proc = _processor_or_422(body.url)
    ref = proc.normalize(body.url)
    try:
        async with domain_slot(proc.domain()):
            inspection = await proc.inspect(ref)
    except FetchError as exc:
        raise HTTPException(502, f"No se pudo leer la página: {exc}") from exc
    product = get_or_create_product(db, proc, ref)
    await apply_result(db, product, inspection.result)

    # {(external_id, variant_id): Watch} de lo que el usuario ya sigue en esta tienda.
    watched = {
        (ext, variant): watch
        for ext, variant, watch in db.execute(
            select(Product.external_id, Product.variant_id, Watch)
            .join(WatchItem, WatchItem.product_id == Product.id)
            .join(Watch, Watch.id == WatchItem.watch_id)
            .where(WatchItem.user_id == user.id, Product.processor == proc.name)
        )
    }

    def watching_in(key: tuple[str, str]) -> dict | None:
        w = watched.get(key)
        return {"id": w.id, "name": groups.display_name(w)} if w else None

    key = (ref.external_id, ref.variant_id)
    return {
        "processor": proc.name,
        "processor_label": proc.label,
        "product": product_out(db, product),
        "already_watching": key in watched,
        "watching_in": watching_in(key),
        "variants_title": proc.variants_title,
        "variants_hint": proc.variants_hint,
        "variants": [
            {
                "url": v.url,
                "label": v.label,
                "external_id": v.external_id,
                "selected": v.selected,
                "already_watching": (v.external_id, v.variant_id) in watched,
                "watching_in": watching_in((v.external_id, v.variant_id)),
            }
            for v in inspection.variants
        ],
    }


# --- Crear / listar / editar ----------------------------------------------------------------
class RuleIn(BaseModel):
    id: int | None = None
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class WatchCreateIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    rules: list[RuleIn] = Field(default_factory=list, max_length=12)
    # separate: un Watch por link (variantes); group: un solo Watch con todos los links.
    mode: Literal["separate", "group"] = "separate"
    name: str | None = Field(default=None, max_length=200)
    category_ids: list[int] = Field(default_factory=list, max_length=200)


def _validated_rules(items: list[RuleIn]) -> list[tuple[RuleIn, dict]]:
    out = []
    for item in items:
        try:
            out.append((item, rules.validate_params(item.kind, item.params)))
        except rules.RuleError as exc:
            raise HTTPException(422, str(exc)) from exc
    return out


def _clean_name(name: str | None) -> str | None:
    return (name or "").strip()[:200] or None


def _already_in(db: DbSession, item: WatchItem, product: Product) -> HTTPException:
    return HTTPException(
        409,
        {
            "code": "already_watching",
            "message": f"«{product.title or product.canonical_url}» ya está en tu producto "
            f"«{groups.display_name(item.watch)}».",
            "watch_id": item.watch_id,
        },
    )


def _check_group(products: list[Product]) -> None:
    if len(products) > MAX_ITEMS:
        raise HTTPException(422, f"Un producto puede tener como máximo {MAX_ITEMS} links.")
    currencies = {p.currency for p in products}
    if len(currencies) > 1:
        raise HTTPException(
            422, f"Todos los links deben tener la misma moneda ({', '.join(sorted(currencies))})."
        )


def reset_group(db: DbSession, watch: Watch) -> None:
    """La lectura del grupo cambió de golpe (se agregó, quitó o juntó un link): las
    reglas toman la lectura nueva sin avisar el salto (ver `groups.recalibrate`)."""
    db.flush()
    db.expire(watch, ["items"])
    groups.recalibrate(db, watch, utcnow())


def _new_watch(
    db: DbSession,
    user: User,
    products: list[Product],
    specs: list[tuple[str, dict, bool]],
    name: str | None = None,
    active: bool = True,
    categories: list[Category] | None = None,
) -> Watch:
    """Watch nuevo con esos productos y reglas (kind, params, enabled) en estado inicial."""
    watch = Watch(user_id=user.id, name=name, active=active)
    db.add(watch)
    watch.items = [WatchItem(product_id=p.id, user_id=user.id) for p in products]
    watch.categories = list(categories or [])
    db.flush()
    states = groups.item_states(db, watch, utcnow())
    best = groups.best_item(states)
    reading = groups.reading_of(best)
    watch.price_at_start = reading.price if reading else None
    groups.remember(watch, reading, best, groups.counted_ids(states))
    for kind, params, enabled in specs:
        db.add(
            AlertRule(
                watch_id=watch.id,
                kind=kind,
                params=params,
                state=rules.initial_state(kind, reading),
                enabled=enabled,
            )
        )
    return watch


@router.post("/watches", status_code=201)
async def create_watches(
    body: WatchCreateIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> list[dict]:
    specs = [(item.kind, params, item.enabled) for item, params in _validated_rules(body.rules)]
    categories = own_categories(db, user, body.category_ids)
    targets: list[tuple[Processor, ProductRef]] = []
    for url in body.urls:
        proc = _processor_or_422(url)
        targets.append((proc, proc.normalize(url)))

    if body.mode == "group":
        products: list[Product] = []
        for proc, ref in targets:
            product = get_or_create_product(db, proc, ref)
            if product in products:
                continue
            item = own_item(db, user, product.id)
            if item is not None:
                raise _already_in(db, item, product)
            products.append(product)
        _check_group(products)
        for product in products:
            await _read_if_new(db, product)
        _check_group(products)  # la moneda se conoce después de la primera lectura
        watch = _new_watch(
            db, user, products, specs, name=_clean_name(body.name), categories=categories
        )
        db.commit()
        db.refresh(watch)
        return [watch_out(db, watch)]

    created: list[Watch] = []
    for proc, ref in targets:
        product = get_or_create_product(db, proc, ref)
        item = own_item(db, user, product.id)
        if item is not None:
            if item.watch not in created:
                created.append(item.watch)
            continue
        await _read_if_new(db, product)
        created.append(_new_watch(db, user, [product], specs, categories=categories))
        db.flush()
    db.commit()
    for w in created:
        db.refresh(w)
    return [watch_out(db, w) for w in created]


@router.get("/watches")
def list_watches(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list:
    watches = db.scalars(
        select(Watch).where(Watch.user_id == user.id).order_by(Watch.created_at.desc())
    )
    return [watch_out(db, w) for w in watches]


@router.get("/watches/{watch_id}")
def get_watch(
    watch_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    return watch_out(db, get_own_watch(db, user, watch_id))


class WatchPatchIn(BaseModel):
    active: bool | None = None
    # "" (o solo espacios) vuelve al título de la tienda.
    name: str | None = Field(default=None, max_length=200)
    rules: list[RuleIn] | None = Field(default=None, max_length=12)
    telegram_enabled: bool | None = None
    # {kind: habilitado} para apagar un canal global solo en este Watch.
    channels: dict[str, bool] | None = None


@router.patch("/watches/{watch_id}")
def update_watch(
    watch_id: int,
    body: WatchPatchIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    watch = get_own_watch(db, user, watch_id)
    if body.active is not None:
        watch.active = body.active
    if "name" in body.model_fields_set:
        watch.name = _clean_name(body.name)
    if body.rules is not None:
        specs = _validated_rules(body.rules)
        current = {r.id: r for r in watch.rules}
        reading, _ = groups.group_reading(db, watch, utcnow())
        keep: list[AlertRule] = []
        for item, params in specs:
            old = current.get(item.id) if item.id else None
            if old is not None and old.kind == item.kind:
                if old.params != params:
                    # Umbral nuevo: la regla parte de cero (re-armada).
                    old.params = params
                    old.state = rules.initial_state(item.kind, reading)
                old.enabled = item.enabled
                keep.append(old)
            else:
                keep.append(
                    AlertRule(
                        kind=item.kind,
                        params=params,
                        enabled=item.enabled,
                        state=rules.initial_state(item.kind, reading),
                    )
                )
        watch.rules = keep
    overrides = dict(body.channels or {})
    if body.telegram_enabled is not None:
        overrides["telegram"] = body.telegram_enabled
    for kind, enabled in overrides.items():
        ch = db.scalar(select(Channel).where(Channel.user_id == user.id, Channel.kind == kind))
        if ch is None:
            raise HTTPException(409, f"Primero conecta {kind.capitalize()} en Ajustes.")
        override = db.get(WatchChannel, (watch.id, ch.id))
        if override is None:
            db.add(WatchChannel(watch_id=watch.id, channel_id=ch.id, enabled=enabled))
        else:
            override.enabled = enabled
    db.commit()
    db.refresh(watch)
    return watch_out(db, watch)


@router.delete("/watches/{watch_id}", status_code=204)
def delete_watch(
    watch_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> None:
    watch = get_own_watch(db, user, watch_id)
    db.delete(watch)
    db.commit()


# --- Links de un Watch: agregar, quitar, mover, juntar ------------------------------------
class ItemIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/watches/{watch_id}/items", status_code=201)
async def add_item(
    watch_id: int,
    body: ItemIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    watch = get_own_watch(db, user, watch_id)
    proc = _processor_or_422(body.url)
    product = get_or_create_product(db, proc, proc.normalize(body.url))
    item = own_item(db, user, product.id)
    if item is not None:
        raise _already_in(db, item, product)
    await _read_if_new(db, product)
    watch = get_own_watch(db, user, watch_id)
    _check_group([i.product for i in watch.items] + [product])
    watch.items.append(WatchItem(product_id=product.id, user_id=user.id))
    reset_group(db, watch)
    db.commit()
    db.refresh(watch)
    return watch_out(db, watch)


def _item_of(watch: Watch, product_id: int) -> WatchItem:
    for item in watch.items:
        if item.product_id == product_id:
            return item
    raise HTTPException(404, "ese link no está en este producto")


def _after_removal(db: DbSession, watch: Watch) -> dict | None:
    """Un Watch que se quedó sin links se borra (la UI lo confirma antes)."""
    db.flush()
    db.expire(watch, ["items"])
    if not watch.items:
        db.delete(watch)
        return None
    reset_group(db, watch)
    return watch


@router.delete("/watches/{watch_id}/items/{product_id}")
def remove_item(
    watch_id: int,
    product_id: int,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    watch = get_own_watch(db, user, watch_id)
    db.delete(_item_of(watch, product_id))
    left = _after_removal(db, watch)
    db.commit()
    return {"watch": watch_out(db, left) if left else None}


class MoveIn(BaseModel):
    # Watch de destino; None = uno nuevo, con una copia de las reglas del de origen.
    to: int | None = None


@router.post("/watches/{watch_id}/items/{product_id}/move")
def move_item(
    watch_id: int,
    product_id: int,
    body: MoveIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    source = get_own_watch(db, user, watch_id)
    item = _item_of(source, product_id)
    if body.to is None:
        if len(source.items) == 1:
            raise HTTPException(409, "Ese link ya es el único de este producto.")
        db.execute(delete(WatchItem).where(WatchItem.id == item.id))
        db.expire(source, ["items"])
        target = _new_watch(
            db,
            user,
            [db.get(Product, product_id)],
            [(r.kind, r.params, r.enabled) for r in source.rules],
            active=source.active,
            categories=source.categories,
        )
        for wc in db.scalars(select(WatchChannel).where(WatchChannel.watch_id == source.id)):
            db.add(WatchChannel(watch_id=target.id, channel_id=wc.channel_id, enabled=wc.enabled))
    else:
        if body.to == source.id:
            raise HTTPException(409, "Ese link ya está en este producto.")
        target = get_own_watch(db, user, body.to)
        _check_group([i.product for i in target.items] + [item.product])
        db.execute(update(WatchItem).where(WatchItem.id == item.id).values(watch_id=target.id))
        if len(source.items) == 1:
            # El de origen se queda vacío y se borra: sus avisos y categorías pasan al destino.
            _join_categories(target, [source])
            db.execute(
                update(Notification)
                .where(Notification.watch_id == source.id)
                .values(watch_id=target.id)
            )
        db.expire(source, ["items"])
        reset_group(db, target)
    left = _after_removal(db, source)
    db.commit()
    db.refresh(target)
    return {"source": watch_out(db, left) if left else None, "target": watch_out(db, target)}


def _join_categories(target: Watch, others: list[Watch]) -> None:
    """El Watch que queda se lleva la unión de las categorías."""
    for w in others:
        for c in w.categories:
            if c not in target.categories:
                target.categories.append(c)


class MergeIn(BaseModel):
    ids: list[int] = Field(min_length=2, max_length=MAX_ITEMS)
    # El que conserva nombre, reglas y canales; por defecto, el más antiguo.
    primary: int | None = None


@router.post("/watches/merge")
def merge_watches(
    body: MergeIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    watches = [get_own_watch(db, user, i) for i in dict.fromkeys(body.ids)]
    if len(watches) < 2:
        raise HTTPException(422, "Elige al menos dos productos para juntar.")
    if body.primary is None:
        primary = min(watches, key=lambda w: (w.created_at, w.id))
    else:
        primary = next((w for w in watches if w.id == body.primary), None)
        if primary is None:
            raise HTTPException(422, "El principal tiene que ser uno de los elegidos.")
    _check_group([i.product for w in watches for i in w.items])
    others = [w for w in watches if w is not primary]
    other_ids = [w.id for w in others]
    _join_categories(primary, others)
    starts = [w.price_at_start for w in watches if w.price_at_start is not None]
    # Con UPDATE directo: los items y avisos cambian de dueño antes de borrar los otros
    # Watches, así el borrado (en cascada) solo se lleva sus reglas y canales.
    db.execute(
        update(WatchItem).where(WatchItem.watch_id.in_(other_ids)).values(watch_id=primary.id)
    )
    db.execute(
        update(Notification).where(Notification.watch_id.in_(other_ids)).values(watch_id=primary.id)
    )
    for w in others:
        db.expire(w)
        db.delete(w)
    primary.price_at_start = min(starts) if starts else None
    reset_group(db, primary)
    db.commit()
    db.refresh(primary)
    return watch_out(db, primary)


# --- Revisar ahora e historial ------------------------------------------------------------
@router.post("/watches/{watch_id}/check")
async def check_now(
    watch_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    """ "Revisar ahora": revisa todos los links, cada uno con su cooldown de 15 min
    (por producto, no por usuario)."""
    watch = get_own_watch(db, user, watch_id)
    products = [i.product for i in watch.items]
    now = utcnow()
    ready = [p for p in products if cooldown_until(p) is None and not is_in_flight(p.id)]
    if not ready:
        waits = [w for w in (cooldown_until(p) for p in products) if w]
        if len(waits) < len(products):
            raise HTTPException(409, "Ya se está revisando este producto.")
        wait = min(waits) - now
        raise HTTPException(
            429,
            {
                "code": "cooldown",
                "message": f"Se revisó hace poco. Intenta de nuevo en {int(wait.total_seconds() // 60) + 1} min.",
                "retry_after_seconds": int(wait.total_seconds()),
            },
        )
    for p in ready:
        p.last_manual_check_at = now
    ids = [p.id for p in ready]
    db.commit()
    outcomes = [await check_product(pid) for pid in ids]
    db.expire_all()
    failed = next((o for o in outcomes if not o.ok), None)
    return {
        "outcome": {
            "ok": failed is None,
            "error": failed.error if failed else None,
            "anomaly": failed.anomaly if failed else None,
            "notifications": sum(len(o.notifications) for o in outcomes),
            "checked": len(outcomes),
        },
        "watch": watch_out(db, get_own_watch(db, user, watch_id)),
    }


@router.get("/watches/{watch_id}/history")
def history(
    watch_id: int,
    days: int = 365,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    """Historial de cada link del Watch (la serie del grupo se arma en el cliente)."""
    watch = get_own_watch(db, user, watch_id)
    since = utcnow() - timedelta(days=max(1, min(days, 3650)))
    out = []
    for item in watch.items:
        product = item.product
        points = db.scalars(
            select(PricePoint)
            .where(PricePoint.product_id == product.id, PricePoint.checked_at >= since)
            .order_by(PricePoint.checked_at)
        )
        out.append(
            {
                "product_id": product.id,
                "processor": product.processor,
                "title": product.title,
                "variant_label": get_processor(product.processor).variant_label(
                    product.external_id, product.variant_id
                ),
                "points": [
                    {
                        "price": p.price,
                        "list_price": p.list_price,
                        "available": p.available,
                        "checked_at": iso(p.checked_at),
                    }
                    for p in points
                ],
            }
        )
    return {"items": out}


# --- Notificaciones -----------------------------------------------------------------------
@router.get("/notifications")
def notifications(
    watch_id: int | None = None,
    limit: int = 100,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    q = (
        select(Notification, Watch)
        .join(Watch, Watch.id == Notification.watch_id)
        .where(Watch.user_id == user.id)
        .order_by(Notification.sent_at.desc(), Notification.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if watch_id is not None:
        q = q.where(Notification.watch_id == watch_id)
    out = []
    for n, w in db.execute(q):
        # El producto del aviso (el ganador); los avisos viejos no lo guardaban.
        product = db.get(Product, n.payload.get("product_id") or 0) or (
            w.items[0].product if w.items else None
        )
        out.append(
            {
                "id": n.id,
                "watch_id": n.watch_id,
                "sent_at": iso(n.sent_at),
                "payload": n.payload,
                "delivery": n.delivery,
                "product": {
                    "processor": product.processor if product else None,
                    "image_url": product.image_url if product else None,
                },
            }
        )
    return out


# --- Tiendas soportadas --------------------------------------------------------------
@router.get("/processors")
def processors(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> list[dict]:
    """Tiendas soportadas, con los productos del usuario y el estado agregado de la tienda.

    El estado (`ok` | `problems` | `unknown`) y la última lectura correcta se calculan
    sobre todos los productos seguidos, sin revelar qué ni cuánto siguen otros usuarios.
    """
    from tracker.processors import PROCESSORS

    mine = dict(
        db.execute(
            select(Product.processor, func.count(WatchItem.id))
            .join(WatchItem, WatchItem.product_id == Product.id)
            .join(Watch, Watch.id == WatchItem.watch_id)
            .where(Watch.user_id == user.id, Watch.active.is_(True))
            .group_by(Product.processor)
        ).all()
    )
    watched = (
        select(WatchItem.product_id)
        .join(Watch, Watch.id == WatchItem.watch_id)
        .where(Watch.active.is_(True))
    )
    broken = set(
        db.scalars(
            select(Product.processor)
            .where(Product.status == "broken", Product.id.in_(watched))
            .distinct()
        )
    )
    last_ok = dict(
        db.execute(
            select(Product.processor, func.max(Product.last_checked_at))
            .where(Product.status == "ok")
            .group_by(Product.processor)
        ).all()
    )
    out = []
    for p in PROCESSORS.values():
        if p.name in broken:
            status = "problems"
        elif last_ok.get(p.name):
            status = "ok"
        else:
            status = "unknown"
        out.append(
            {
                "name": p.name,
                "label": p.label,
                "check_interval_hours": p.check_interval.total_seconds() / 3600,
                "home_url": p.home_url,
                "domain": p.domain(),
                "example_url": p.example_url,
                "platform": p.platform,
                "supports_variants": p.supports_variants,
                "supports_list_price": p.supports_list_price,
                "slow": p.slow,
                "notes": p.notes,
                "logo_url": logos.logo_url(logos.get_logo(db, p.name), p.name),
                "my_watches": mine.get(p.name, 0),
                "status": status,
                "last_ok_at": iso(last_ok.get(p.name)),
            }
        )
    return out


@router.get("/processors/{name}/logo")
def processor_logo(
    name: str,
    request: Request,
    _: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> Response:
    """PNG del logo. La URL lleva `?v=<hash>`, así que se puede cachear sin vencimiento."""
    from tracker.processors import PROCESSORS

    logo = logos.get_logo(db, name) if name in PROCESSORS else None
    if logo is None:
        raise HTTPException(404, "sin logo")
    headers = {"ETag": f'"{logo.etag}"', "Cache-Control": "private, max-age=31536000, immutable"}
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    return Response(logo.data, media_type="image/png", headers=headers)
