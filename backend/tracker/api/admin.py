"""Panel admin: usuarios, productos seguidos por cada usuario, tiendas y métricas.

Desde el 2026-09-29 el admin sí ve qué productos sigue cada usuario (decisión del
dueño de la instancia; antes solo veía métricas agregadas). Los usuarios entre sí
siguen sin verse.
"""

import re
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker import logos, meli
from tracker.api.deps import require_admin
from tracker.api.watches import latest_point, product_out, rule_out
from tracker.config import settings
from tracker.db import get_db, utcnow
from tracker.models import (
    Anomaly,
    Invite,
    Notification,
    PricePoint,
    Product,
    User,
    Watch,
)
from tracker.processors import PROCESSORS
from tracker.security import create_invite, revoke_sessions

router = APIRouter(prefix="/api/admin", tags=["admin"])
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


def iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def user_out(db: DbSession, u: User) -> dict:
    invite = db.scalar(
        select(Invite)
        .where(Invite.user_id == u.id, Invite.used_at.is_(None), Invite.expires_at > utcnow())
        .order_by(Invite.expires_at.desc())
        .limit(1)
    )
    week = utcnow() - timedelta(days=7)
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "active": u.active,
        "watch_quota": u.watch_quota,
        "watch_count": db.scalar(select(func.count(Watch.id)).where(Watch.user_id == u.id)),
        "active_watch_count": db.scalar(
            select(func.count(Watch.id)).where(Watch.user_id == u.id, Watch.active.is_(True))
        ),
        "notifications_7d": db.scalar(
            select(func.count(Notification.id))
            .join(Watch, Watch.id == Notification.watch_id)
            .where(Watch.user_id == u.id, Notification.sent_at >= week)
        ),
        "has_password": u.password_hash is not None,
        "pending_invite_expires_at": iso(invite.expires_at) if invite else None,
        "created_at": iso(u.created_at),
    }


@router.get("/users")
def list_users(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> list:
    return [user_out(db, u) for u in db.scalars(select(User).order_by(User.id))]


class UserCreateIn(BaseModel):
    username: str
    role: str = "user"


@router.post("/users", status_code=201)
def create_user(
    body: UserCreateIn, _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> dict:
    username = body.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(422, "usuario: 3-32 caracteres a-z, 0-9, _ . -")
    if body.role not in ("admin", "user"):
        raise HTTPException(422, "rol inválido")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "ese usuario ya existe")
    user = User(username=username, role=body.role, active=True)
    db.add(user)
    db.flush()
    link = create_invite(db, user)
    db.commit()
    return {"user": user_out(db, user), "invite_url": link}


@router.post("/users/{user_id}/invite")
def reinvite(
    user_id: int, _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "no existe")
    link = create_invite(db, user)
    db.commit()
    return {"invite_url": link, "user": user_out(db, user)}


class UserPatchIn(BaseModel):
    active: bool | None = None
    watch_quota: int | None = Field(default=None, ge=0, le=10000)
    role: str | None = None


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserPatchIn,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "no existe")
    if user.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(409, "no puedes desactivarte ni quitarte el rol de admin")
    if body.active is not None:
        user.active = body.active
        if not body.active:
            # Desactivar = sesiones revocadas al instante; sus Watch quedan pausados
            # porque el scheduler ignora a los usuarios inactivos. Reversible.
            revoke_sessions(db, user.id)
    if body.watch_quota is not None:
        user.watch_quota = body.watch_quota
    if body.role is not None:
        if body.role not in ("admin", "user"):
            raise HTTPException(422, "rol inválido")
        user.role = body.role
    db.commit()
    return user_out(db, user)


@router.get("/products")
def products(
    status: str = "broken", _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> list:
    q = select(Product).order_by(Product.last_checked_at.desc())
    if status != "all":
        q = q.where(Product.status == status)
    out = []
    for p in db.scalars(q.limit(500)):
        point = latest_point(db, p.id)
        followers = list(
            db.scalars(
                select(User.username)
                .join(Watch, Watch.user_id == User.id)
                .where(Watch.product_id == p.id)
                .order_by(User.username)
            )
        )
        out.append(
            {
                "id": p.id,
                "processor": p.processor,
                "title": p.title,
                "url": p.canonical_url,
                "image_url": p.image_url,
                "currency": p.currency,
                "price": point.price if point else None,
                "available": point.available if point else None,
                "status": p.status,
                "fail_count": p.fail_count,
                "last_error": p.last_error,
                "last_checked_at": iso(p.last_checked_at),
                "next_check_at": iso(p.next_check_at),
                "watchers": len(followers),
                "followers": followers,
            }
        )
    return out


@router.get("/watches")
def watches(
    user_id: int | None = None,
    _: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> list:
    """Productos que sigue cada usuario (o uno), con reglas y avisos recientes."""
    week = utcnow() - timedelta(days=7)
    q = (
        select(Watch, User.username)
        .join(User, User.id == Watch.user_id)
        .order_by(User.username, Watch.created_at.desc())
    )
    if user_id is not None:
        q = q.where(Watch.user_id == user_id)
    out = []
    for w, username in db.execute(q):
        last_notif = db.scalar(
            select(func.max(Notification.sent_at)).where(Notification.watch_id == w.id)
        )
        out.append(
            {
                "id": w.id,
                "user": {"id": w.user_id, "username": username},
                "active": w.active,
                "created_at": iso(w.created_at),
                "price_at_start": w.price_at_start,
                "product": product_out(db, w.product),
                "rules": [rule_out(r) for r in w.rules],
                "notifications_7d": db.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.watch_id == w.id, Notification.sent_at >= week
                    )
                ),
                "last_notification_at": iso(last_notif),
            }
        )
    return out


@router.get("/stores")
def stores(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> list:
    """Salud y uso por tienda (procesador)."""
    week = utcnow() - timedelta(days=7)

    def per_processor(q) -> dict:
        return dict(db.execute(q.group_by(Product.processor)).all())

    products_n = per_processor(select(Product.processor, func.count(Product.id)))
    watches_n = per_processor(
        select(Product.processor, func.count(Watch.id)).join(Watch, Watch.product_id == Product.id)
    )
    users_n = per_processor(
        select(Product.processor, func.count(func.distinct(Watch.user_id))).join(
            Watch, Watch.product_id == Product.id
        )
    )
    broken_n = per_processor(
        select(Product.processor, func.count(Product.id)).where(Product.status == "broken")
    )
    failing_n = per_processor(
        select(Product.processor, func.count(Product.id)).where(Product.fail_count > 0)
    )
    anomalies_n = per_processor(
        select(Product.processor, func.count(Anomaly.id))
        .join(Anomaly, Anomaly.product_id == Product.id)
        .where(Anomaly.created_at >= week)
    )
    last_ok = per_processor(
        select(Product.processor, func.max(Product.last_checked_at)).where(Product.status == "ok")
    )
    store_logos = {name: logos.get_logo(db, name) for name in PROCESSORS}
    return [
        {
            "name": p.name,
            "label": p.label,
            "domain": p.domain(),
            "logo_url": logos.logo_url(store_logos[p.name], p.name),
            "logo_custom": bool(store_logos[p.name] and store_logos[p.name].custom),
            "check_interval_hours": p.check_interval.total_seconds() / 3600,
            "products": products_n.get(p.name, 0),
            "watches": watches_n.get(p.name, 0),
            "users": users_n.get(p.name, 0),
            "broken": broken_n.get(p.name, 0),
            "failing": failing_n.get(p.name, 0),
            "anomalies_7d": anomalies_n.get(p.name, 0),
            "last_ok_at": iso(last_ok.get(p.name)),
        }
        for p in PROCESSORS.values()
    ]


def _processor_or_404(name: str) -> str:
    if name not in PROCESSORS:
        raise HTTPException(404, "no existe esa tienda")
    return name


@router.put("/stores/{name}/logo")
async def upload_logo(
    name: str,
    request: Request,
    _: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Reemplaza el logo: el cuerpo es el PNG tal cual (Content-Type: image/png)."""
    _processor_or_404(name)
    if request.headers.get("content-type", "").split(";")[0].strip() != "image/png":
        raise HTTPException(415, "el logo debe ser un PNG")
    try:
        logo = logos.set_logo(db, name, await request.body())
    except logos.LogoError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"logo_url": logos.logo_url(logo, name), "logo_custom": True}


@router.delete("/stores/{name}/logo")
def reset_logo(
    name: str, _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> dict:
    """Vuelve al logo por defecto (el del código), si existe."""
    _processor_or_404(name)
    logos.reset_logo(db, name)
    return {"logo_url": logos.logo_url(logos.get_logo(db, name), name), "logo_custom": False}


@router.post("/products/{product_id}/retry")
def retry_product(
    product_id: int, _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> dict:
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "no existe")
    p.next_check_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/anomalies")
def anomalies(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> list:
    rows = db.execute(
        select(Anomaly, Product)
        .join(Product, Product.id == Anomaly.product_id)
        .order_by(Anomaly.created_at.desc())
        .limit(200)
    )
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "detail": a.detail,
            "created_at": iso(a.created_at),
            "product": {
                "id": p.id,
                "title": p.title,
                "processor": p.processor,
                "url": p.canonical_url,
            },
        }
        for a, p in rows
    ]


@router.get("/metrics")
def metrics(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> dict:
    now = utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)

    def count(q):
        return db.scalar(q) or 0

    by_processor = {
        name: n
        for name, n in db.execute(
            select(Product.processor, func.count(Product.id)).group_by(Product.processor)
        )
    }
    return {
        "users": count(select(func.count(User.id))),
        "active_users": count(select(func.count(User.id)).where(User.active.is_(True))),
        "watches": count(select(func.count(Watch.id))),
        "active_watches": count(select(func.count(Watch.id)).where(Watch.active.is_(True))),
        "products": count(select(func.count(Product.id))),
        "products_by_processor": by_processor,
        "broken_products": count(select(func.count(Product.id)).where(Product.status == "broken")),
        "failing_products": count(select(func.count(Product.id)).where(Product.fail_count > 0)),
        "price_points_24h": count(
            select(func.count(PricePoint.id)).where(PricePoint.checked_at >= day)
        ),
        "notifications_7d": count(
            select(func.count(Notification.id)).where(Notification.sent_at >= week)
        ),
        "anomalies_7d": count(select(func.count(Anomaly.id)).where(Anomaly.created_at >= week)),
    }


# --- MercadoLibre (OAuth) -------------------------------------------------------------
@router.get("/meli")
def meli_status(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> dict:
    return meli.status(db)


@router.get("/meli/connect")
def meli_connect(_: User = Depends(require_admin)) -> RedirectResponse:
    """Redirige a MercadoLibre para aprobar la app (navegación, no fetch)."""
    if not meli.configured():
        raise HTTPException(503, "Falta MELI_CLIENT_ID / MELI_CLIENT_SECRET en el .env")
    return RedirectResponse(meli.authorization_url(), status_code=302)


@router.get("/meli/callback")
async def meli_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    _: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> RedirectResponse:
    """MercadoLibre vuelve aquí con `code` y `state`; se canjea y se vuelve al panel."""
    back = f"{settings.public_url}/admin/tiendas"
    if error or not code:
        return RedirectResponse(f"{back}?meli=error&msg={quote(error or 'sin código')}", 302)
    try:
        await meli.complete_authorization(db, code, state)
    except meli.MeliError as exc:
        return RedirectResponse(f"{back}?meli=error&msg={quote(str(exc)[:200])}", 302)
    return RedirectResponse(f"{back}?meli=ok", 302)
