"""Watches del usuario: agregar por link, reglas, historial y "Revisar ahora".

Privacidad: toda consulta filtra por `Watch.user_id == user.id`.
"""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker import logos, rules
from tracker.api.deps import current_user
from tracker.checker import apply_result, check_product, domain_slot, is_in_flight
from tracker.config import settings
from tracker.db import get_db, utcnow
from tracker.models import (
    AlertRule,
    Channel,
    Notification,
    PricePoint,
    Product,
    User,
    Watch,
    WatchChannel,
)
from tracker.processors import FetchError, Processor, ProductRef, find_processor

router = APIRouter(prefix="/api", tags=["watches"])


def iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# --- Serialización -----------------------------------------------------------------
def latest_point(db: DbSession, product_id: int) -> PricePoint | None:
    return db.scalar(
        select(PricePoint)
        .where(PricePoint.product_id == product_id)
        .order_by(PricePoint.checked_at.desc(), PricePoint.id.desc())
        .limit(1)
    )


def product_out(db: DbSession, product: Product) -> dict:
    point = latest_point(db, product.id)
    min_price = db.scalar(
        select(func.min(PricePoint.price)).where(
            PricePoint.product_id == product.id, PricePoint.price.is_not(None)
        )
    )
    cooldown_until = None
    if product.last_manual_check_at:
        until = product.last_manual_check_at + timedelta(minutes=settings.manual_check_cooldown_min)
        if until > utcnow():
            cooldown_until = iso(until)
    from tracker.processors import get_processor

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
        "manual_check_available_at": cooldown_until,
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
    return {
        "id": watch.id,
        "active": watch.active,
        "created_at": iso(watch.created_at),
        "price_at_start": watch.price_at_start,
        "product": product_out(db, watch.product),
        "rules": [rule_out(r) for r in watch.rules],
        "channels": channels,
        # Compatibilidad con la UI de la v0.
        "telegram_enabled": channels.get("telegram"),
    }


def get_own_watch(db: DbSession, user: User, watch_id: int) -> Watch:
    watch = db.get(Watch, watch_id)
    # 404 también si es de otro usuario: no se revela que existe.
    if watch is None or watch.user_id != user.id:
        raise HTTPException(404, "no existe")
    return watch


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

    watched = {
        (ext, variant)
        for ext, variant in db.execute(
            select(Product.external_id, Product.variant_id)
            .join(Watch, Watch.product_id == Product.id)
            .where(Watch.user_id == user.id, Product.processor == proc.name)
        )
    }
    return {
        "processor": proc.name,
        "processor_label": proc.label,
        "product": product_out(db, product),
        "already_watching": (ref.external_id, ref.variant_id) in watched,
        "variants_title": proc.variants_title,
        "variants_hint": proc.variants_hint,
        "variants": [
            {
                "url": v.url,
                "label": v.label,
                "external_id": v.external_id,
                "selected": v.selected,
                "already_watching": (v.external_id, v.variant_id) in watched,
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


def _validated_rules(items: list[RuleIn]) -> list[tuple[RuleIn, dict]]:
    out = []
    for item in items:
        try:
            out.append((item, rules.validate_params(item.kind, item.params)))
        except rules.RuleError as exc:
            raise HTTPException(422, str(exc)) from exc
    return out


def _reading_of(point: PricePoint | None) -> rules.Reading | None:
    return rules.Reading(point.price, point.list_price, point.available) if point else None


@router.post("/watches", status_code=201)
async def create_watches(
    body: WatchCreateIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> list[dict]:
    specs = _validated_rules(body.rules)
    targets: list[tuple[Processor, ProductRef]] = []
    for url in body.urls:
        proc = _processor_or_422(url)
        targets.append((proc, proc.normalize(url)))

    created: list[Watch] = []
    for proc, ref in targets:
        product = get_or_create_product(db, proc, ref)
        watch = db.scalar(
            select(Watch).where(Watch.user_id == user.id, Watch.product_id == product.id)
        )
        if watch is not None:
            created.append(watch)
            continue
        # Una variante hermana que nunca se leyó: se lee ahora para tener precio de inicio.
        if latest_point(db, product.id) is None:
            db.commit()
            await check_product(product.id)
            db.expire_all()
        point = latest_point(db, product.id)
        watch = Watch(
            user_id=user.id,
            product_id=product.id,
            active=True,
            price_at_start=point.price if point else None,
        )
        db.add(watch)
        db.flush()
        reading = _reading_of(point)
        for item, params in specs:
            db.add(
                AlertRule(
                    watch_id=watch.id,
                    kind=item.kind,
                    params=params,
                    state=rules.initial_state(item.kind, reading),
                    enabled=item.enabled,
                )
            )
        created.append(watch)
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
    if body.rules is not None:
        specs = _validated_rules(body.rules)
        current = {r.id: r for r in watch.rules}
        reading = _reading_of(latest_point(db, watch.product_id))
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


@router.post("/watches/{watch_id}/check")
async def check_now(
    watch_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    """ "Revisar ahora": cooldown de 15 min por producto (no por usuario)."""
    watch = get_own_watch(db, user, watch_id)
    product = watch.product
    now = utcnow()
    cooldown = timedelta(minutes=settings.manual_check_cooldown_min)
    if product.last_manual_check_at and now - product.last_manual_check_at < cooldown:
        wait = cooldown - (now - product.last_manual_check_at)
        raise HTTPException(
            429,
            {
                "code": "cooldown",
                "message": f"Se revisó hace poco. Intenta de nuevo en {int(wait.total_seconds() // 60) + 1} min.",
                "retry_after_seconds": int(wait.total_seconds()),
            },
        )
    if is_in_flight(product.id):
        raise HTTPException(409, "Ya se está revisando este producto.")
    product.last_manual_check_at = now
    db.commit()
    outcome = await check_product(product.id)
    db.expire_all()
    return {
        "outcome": {
            "ok": outcome.ok,
            "error": outcome.error,
            "anomaly": outcome.anomaly,
            "notifications": len(outcome.notifications),
        },
        "watch": watch_out(db, get_own_watch(db, user, watch_id)),
    }


@router.get("/watches/{watch_id}/history")
def history(
    watch_id: int,
    days: int = 365,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    watch = get_own_watch(db, user, watch_id)
    since = utcnow() - timedelta(days=max(1, min(days, 3650)))
    points = db.scalars(
        select(PricePoint)
        .where(PricePoint.product_id == watch.product_id, PricePoint.checked_at >= since)
        .order_by(PricePoint.checked_at)
    )
    return [
        {
            "price": p.price,
            "list_price": p.list_price,
            "available": p.available,
            "checked_at": iso(p.checked_at),
        }
        for p in points
    ]


# --- Notificaciones -----------------------------------------------------------------------
@router.get("/notifications")
def notifications(
    watch_id: int | None = None,
    limit: int = 100,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    q = (
        select(Notification, Product)
        .join(Watch, Watch.id == Notification.watch_id)
        .join(Product, Product.id == Watch.product_id)
        .where(Watch.user_id == user.id)
        .order_by(Notification.sent_at.desc(), Notification.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if watch_id is not None:
        q = q.where(Notification.watch_id == watch_id)
    return [
        {
            "id": n.id,
            "watch_id": n.watch_id,
            "sent_at": iso(n.sent_at),
            "payload": n.payload,
            "delivery": n.delivery,
            "product": {"processor": p.processor, "image_url": p.image_url},
        }
        for n, p in db.execute(q)
    ]


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
            select(Product.processor, func.count(Watch.id))
            .join(Watch, Watch.product_id == Product.id)
            .where(Watch.user_id == user.id, Watch.active.is_(True))
            .group_by(Product.processor)
        ).all()
    )
    watched = select(Watch.product_id).where(Watch.active.is_(True))
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
