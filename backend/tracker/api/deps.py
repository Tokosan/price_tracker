"""Dependencias de FastAPI: usuario actual, admin y protección CSRF."""

import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from tracker.db import get_db
from tracker.models import User
from tracker.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, lookup_session

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double submit: el header X-CSRF-Token debe coincidir con la cookie tracker_csrf.

    Otro sitio no puede leer la cookie ni poner el header, así que no puede
    forjar peticiones. Además, con sesión, el token debe ser el de esa sesión
    (lo comprueba `current_user`).
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return JSONResponse({"detail": "token CSRF inválido"}, status_code=403)
        return await call_next(request)


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    sess = lookup_session(db, request.cookies.get(SESSION_COOKIE))
    if sess is None:
        raise HTTPException(401, "no autenticado")
    if request.method in UNSAFE and not hmac.compare_digest(
        sess.csrf_token, request.headers.get(CSRF_HEADER, "")
    ):
        raise HTTPException(403, "token CSRF inválido para esta sesión")
    request.state.session = sess
    return sess.user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "solo para admin")
    return user
