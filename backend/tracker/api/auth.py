"""Login, logout, invitaciones y sesión actual."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tracker.api.deps import current_user
from tracker.config import settings
from tracker.db import get_db, utcnow
from tracker.models import Channel, User, Watch
from tracker.notifications import discord, telegram
from tracker.security import (
    CSRF_COOKIE,
    MIN_PASSWORD_LEN,
    SESSION_COOKIE,
    create_session,
    hash_password,
    lookup_invite,
    new_token,
    revoke_sessions,
    verify_dummy,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class InviteAcceptIn(BaseModel):
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    max_age = settings.session_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # Legible por JS a propósito: el frontend la copia al header X-CSRF-Token.
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(422, f"la contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres")


@router.get("/csrf")
def csrf(request: Request, response: Response) -> dict:
    """Entrega una cookie CSRF para las peticiones sin sesión (login, invitación)."""
    token = request.cookies.get(CSRF_COOKIE) or new_token()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbSession = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None:
        verify_dummy(body.password)
        raise HTTPException(401, "usuario o contraseña incorrectos")
    if not user.active or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "usuario o contraseña incorrectos")
    token, sess = create_session(db, user)
    db.commit()
    _set_session_cookies(response, token, sess.csrf_token)
    return {"ok": True}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    sess = db.merge(request.state.session)
    db.delete(sess)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/invite/{token}")
def invite_info(token: str, db: DbSession = Depends(get_db)) -> dict:
    inv = lookup_invite(db, token)
    if inv is None or not inv.user.active:
        raise HTTPException(404, "la invitación no existe, ya se usó o expiró")
    return {"username": inv.user.username, "expires_at": inv.expires_at.isoformat() + "Z"}


@router.post("/invite/{token}")
def invite_accept(
    token: str, body: InviteAcceptIn, response: Response, db: DbSession = Depends(get_db)
) -> dict:
    inv = lookup_invite(db, token)
    if inv is None or not inv.user.active:
        raise HTTPException(404, "la invitación no existe, ya se usó o expiró")
    _check_password(body.password)
    user = inv.user
    user.password_hash = hash_password(body.password)
    inv.used_at = utcnow()
    # Una invitación también sirve de reset: cierra las sesiones anteriores.
    revoke_sessions(db, user.id)
    token_value, sess = create_session(db, user)
    db.commit()
    _set_session_cookies(response, token_value, sess.csrf_token)
    return {"ok": True, "username": user.username}


@router.post("/password")
def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    user = db.merge(user)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(401, "la contraseña actual no es correcta")
    _check_password(body.new_password)
    user.password_hash = hash_password(body.new_password)
    revoke_sessions(db, user.id)
    token_value, sess = create_session(db, user)
    db.commit()
    _set_session_cookies(response, token_value, sess.csrf_token)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: DbSession = Depends(get_db)) -> dict:
    watch_count = db.scalar(select(func.count(Watch.id)).where(Watch.user_id == user.id))
    channel = db.scalar(
        select(Channel).where(Channel.user_id == user.id, Channel.kind == "telegram")
    )
    dc = db.scalar(select(Channel).where(Channel.user_id == user.id, Channel.kind == "discord"))
    bot = telegram.bot
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "watch_quota": user.watch_quota,
        "watch_count": watch_count,
        "telegram": {
            "configured": bot is not None,
            "bot_username": bot.username if bot else None,
            "linked": channel is not None,
            "enabled": bool(channel and channel.enabled),
            "channel_id": channel.id if channel else None,
            "chat_username": (channel.config or {}).get("username") if channel else None,
        },
        "discord": {
            "linked": dc is not None,
            "enabled": bool(dc and dc.enabled),
            "channel_id": dc.id if dc else None,
            "label": discord.mask_webhook(dc.config.get("webhook_url", "")) if dc else None,
        },
    }
