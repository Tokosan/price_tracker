"""Contraseñas (argon2), tokens de un solo uso y sesiones en el servidor."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from tracker.config import settings
from tracker.db import utcnow
from tracker.models import Invite, Session, User

_hasher = PasswordHasher()

SESSION_COOKIE = "tracker_session"
CSRF_COOKIE = "tracker_csrf"
CSRF_HEADER = "x-csrf-token"
MIN_PASSWORD_LEN = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Hash de referencia para igualar tiempos cuando el usuario no existe.
_DUMMY_HASH = _hasher.hash("contraseña-de-relleno")


def verify_dummy(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """HMAC del token: en la DB nunca queda el token en claro."""
    return hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def create_session(db: DbSession, user: User) -> tuple[str, Session]:
    token = new_token()
    sess = Session(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_token=new_token(),
        expires_at=utcnow() + timedelta(days=settings.session_days),
    )
    db.add(sess)
    db.flush()
    return token, sess


def lookup_session(db: DbSession, token: str | None) -> Session | None:
    if not token:
        return None
    sess = db.scalar(select(Session).where(Session.token_hash == token_hash(token)))
    if sess is None or sess.expires_at < utcnow():
        return None
    if not sess.user.active:
        return None
    return sess


def revoke_sessions(db: DbSession, user_id: int) -> None:
    db.execute(delete(Session).where(Session.user_id == user_id))


def create_invite(db: DbSession, user: User, hours: int | None = None) -> str:
    """Crea un link de invitación de un solo uso. Invalida las invitaciones previas."""
    now = utcnow()
    for old in db.scalars(
        select(Invite).where(Invite.user_id == user.id, Invite.used_at.is_(None))
    ):
        old.used_at = now
    token = new_token()
    db.add(
        Invite(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now + timedelta(hours=hours or settings.invite_hours),
        )
    )
    db.flush()
    return f"{settings.public_url}/invite/{token}"


def lookup_invite(db: DbSession, token: str) -> Invite | None:
    inv = db.scalar(select(Invite).where(Invite.token_hash == token_hash(token)))
    if inv is None or inv.used_at is not None or inv.expires_at < utcnow():
        return None
    return inv
