"""Cliente OAuth de MercadoLibre (flujo authorization code + PKCE, solo lectura).

La API de MercadoLibre no tiene token "de aplicación": el admin conecta su cuenta
una vez desde el panel (`/api/admin/meli/connect`) y el backend guarda el access
token (6 h) y el refresh token (de un solo uso) en `oauth_tokens`. `access_token()`
renueva solo cuando falta poco para que expire, bajo un lock: dos renovaciones en
paralelo gastarían el mismo refresh token y la segunda dejaría la conexión rota.
"""

import asyncio
import base64
import hashlib
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session as DbSession

from tracker.config import settings
from tracker.db import SessionLocal, utcnow
from tracker.models import OAuthToken

PROVIDER = "meli"
AUTH_URL = "https://auth.mercadolibre.cl/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
API = "https://api.mercadolibre.com"
# Se renueva si al token le queda menos que esto.
REFRESH_MARGIN = timedelta(minutes=10)
PENDING_TTL_S = 600

# Transporte HTTP inyectable para tests (None = red real).
_transport: httpx.AsyncBaseTransport | None = None
_refresh_lock = asyncio.Lock()
# state → (code_verifier, creado en). En memoria: hay un solo proceso, y si se
# reinicia a mitad de una conexión basta con volver a tocar "Conectar".
_pending: dict[str, tuple[str, float]] = {}


class MeliError(Exception):
    """Fallo de OAuth o de la API de MercadoLibre."""


class NotConnectedError(MeliError):
    """No hay cuenta conectada (o la conexión se perdió y hay que reconectar)."""


def configured() -> bool:
    return bool(settings.meli_client_id and settings.meli_client_secret)


def authorization_url() -> str:
    """URL a la que se redirige al admin para aprobar la app (con PKCE S256)."""
    now = time.monotonic()
    for key, (_, created) in list(_pending.items()):
        if now - created > PENDING_TTL_S:
            del _pending[key]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    _pending[state] = (verifier, now)
    query = {
        "response_type": "code",
        "client_id": settings.meli_client_id,
        "redirect_uri": settings.meli_redirect_uri,
        "state": state,
        "code_challenge": challenge.rstrip(b"=").decode(),
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


async def _token_request(data: dict) -> dict:
    payload = {
        "client_id": settings.meli_client_id,
        "client_secret": settings.meli_client_secret,
        **data,
    }
    try:
        async with httpx.AsyncClient(timeout=20, transport=_transport) as client:
            resp = await client.post(
                TOKEN_URL, data=payload, headers={"accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        raise MeliError(f"MercadoLibre no responde: {exc!r}") from exc
    try:
        body = resp.json()
    except ValueError as exc:
        raise MeliError(f"respuesta inválida de /oauth/token (HTTP {resp.status_code})") from exc
    if resp.status_code != 200 or "access_token" not in body:
        raise MeliError(f"{body.get('error', resp.status_code)}: {body.get('message', '')}".strip())
    return body


def _save(db: DbSession, body: dict) -> OAuthToken:
    tok = db.get(OAuthToken, PROVIDER) or OAuthToken(provider=PROVIDER)
    tok.access_token = body["access_token"]
    # Si una renovación no trae refresh token nuevo, se conserva el anterior.
    tok.refresh_token = body.get("refresh_token") or tok.refresh_token
    tok.expires_at = utcnow() + timedelta(seconds=int(body.get("expires_in", 21600)))
    tok.account_id = str(body.get("user_id", tok.account_id or ""))
    tok.scope = body.get("scope", tok.scope or "")
    tok.updated_at = utcnow()
    db.add(tok)
    db.commit()
    return tok


async def complete_authorization(db: DbSession, code: str, state: str) -> OAuthToken:
    pending = _pending.pop(state, None)
    if pending is None or time.monotonic() - pending[1] > PENDING_TTL_S:
        raise MeliError("la solicitud de conexión expiró o no es válida; vuelve a intentarlo")
    body = await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.meli_redirect_uri,
            "code_verifier": pending[0],
        }
    )
    return _save(db, body)


async def access_token() -> str:
    """Access token vigente; lo renueva si está por expirar."""
    with SessionLocal() as db:
        tok = db.get(OAuthToken, PROVIDER)
        if tok is None:
            raise NotConnectedError("MercadoLibre no está conectado (panel admin)")
        if tok.expires_at - utcnow() > REFRESH_MARGIN:
            return tok.access_token
    async with _refresh_lock:
        with SessionLocal() as db:
            tok = db.get(OAuthToken, PROVIDER)
            # Otro llamado pudo renovarlo mientras se esperaba el lock.
            if tok.expires_at - utcnow() > REFRESH_MARGIN:
                return tok.access_token
            if not tok.refresh_token:
                raise NotConnectedError("sin refresh token: reconecta MercadoLibre")
            try:
                body = await _token_request(
                    {"grant_type": "refresh_token", "refresh_token": tok.refresh_token}
                )
            except MeliError as exc:
                if "invalid_grant" in str(exc):
                    raise NotConnectedError(f"hay que reconectar MercadoLibre ({exc})") from exc
                raise
            return _save(db, body).access_token


async def get(path: str, params: dict | None = None) -> httpx.Response:
    """GET autenticado a la API. Devuelve la respuesta tal cual (el llamador decide)."""
    token = await access_token()
    try:
        async with httpx.AsyncClient(timeout=20, transport=_transport) as client:
            return await client.get(
                f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.HTTPError as exc:
        raise MeliError(f"MercadoLibre no responde: {exc!r}") from exc


def status(db: DbSession) -> dict:
    tok = db.get(OAuthToken, PROVIDER)
    return {
        "configured": configured(),
        "connected": tok is not None,
        "account_id": tok.account_id if tok else None,
        "scope": tok.scope if tok else None,
        "can_refresh": bool(tok and tok.refresh_token),
        "expires_at": tok.expires_at.isoformat() + "Z" if tok else None,
    }
