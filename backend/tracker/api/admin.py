"""Panel admin. Nunca expone qué sigue cada usuario: solo métricas agregadas."""

import re
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker import meli
from tracker.api.deps import require_admin
from tracker.config import settings
from tracker.db import get_db, utcnow
from tracker.models import (
    Anomaly,
    Invite,
    Notification,
    PricePoint,
    Product,
    SiteRequest,
    User,
    Watch,
)
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
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "active": u.active,
        "watch_quota": u.watch_quota,
        "watch_count": db.scalar(select(func.count(Watch.id)).where(Watch.user_id == u.id)),
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


@router.get("/site-requests")
def site_requests(_: User = Depends(require_admin), db: DbSession = Depends(get_db)) -> list:
    rows = db.execute(
        select(SiteRequest, User.username)
        .join(User, User.id == SiteRequest.user_id)
        .order_by(SiteRequest.created_at.desc())
    )
    return [
        {
            "id": r.id,
            "url": r.url,
            "note": r.note,
            "status": r.status,
            "username": username,
            "created_at": iso(r.created_at),
        }
        for r, username in rows
    ]


class SiteRequestPatchIn(BaseModel):
    status: str


@router.patch("/site-requests/{req_id}")
def update_site_request(
    req_id: int,
    body: SiteRequestPatchIn,
    _: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    if body.status not in ("pending", "done", "rejected"):
        raise HTTPException(422, "estado inválido")
    req = db.get(SiteRequest, req_id)
    if req is None:
        raise HTTPException(404, "no existe")
    req.status = body.status
    db.commit()
    return {"id": req.id, "status": req.status}


@router.get("/products")
def products(
    status: str = "broken", _: User = Depends(require_admin), db: DbSession = Depends(get_db)
) -> list:
    q = select(Product).order_by(Product.last_checked_at.desc())
    if status != "all":
        q = q.where(Product.status == status)
    return [
        {
            "id": p.id,
            "processor": p.processor,
            "title": p.title,
            "url": p.canonical_url,
            "status": p.status,
            "fail_count": p.fail_count,
            "last_error": p.last_error,
            "last_checked_at": iso(p.last_checked_at),
            "next_check_at": iso(p.next_check_at),
            # Cuántos lo siguen, sin decir quiénes.
            "watchers": db.scalar(select(func.count(Watch.id)).where(Watch.product_id == p.id)),
        }
        for p in db.scalars(q.limit(200))
    ]


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
        "pending_site_requests": count(
            select(func.count(SiteRequest.id)).where(SiteRequest.status == "pending")
        ),
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
    back = f"{settings.public_url}/admin"
    if error or not code:
        return RedirectResponse(f"{back}?meli=error&msg={quote(error or 'sin código')}", 302)
    try:
        await meli.complete_authorization(db, code, state)
    except meli.MeliError as exc:
        return RedirectResponse(f"{back}?meli=error&msg={quote(str(exc)[:200])}", 302)
    return RedirectResponse(f"{back}?meli=ok", 302)
