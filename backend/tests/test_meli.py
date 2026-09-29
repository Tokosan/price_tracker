"""OAuth de MercadoLibre con transporte HTTP simulado (sin red)."""

import asyncio
import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.test_api import logged_in, sin_red  # noqa: F401
from tracker import meli
from tracker.config import settings
from tracker.db import SessionLocal, utcnow
from tracker.models import OAuthToken


@pytest.fixture
def token_api(monkeypatch):
    """Simula /oauth/token; registra cada request y responde según `replies`."""
    monkeypatch.setattr(settings, "meli_client_id", "123")
    monkeypatch.setattr(settings, "meli_client_secret", "secreto")
    calls, replies = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        calls.append(form)
        status, body = replies.pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(meli, "_transport", httpx.MockTransport(handler))
    meli._pending.clear()
    return calls, replies


def granted(access="APP_USR-1", refresh="TG-1", expires_in=21600):
    return 200, {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": expires_in,
        "scope": "offline_access read",
        "user_id": 42,
        "refresh_token": refresh,
    }


def connect(api):
    r = api.get("/api/admin/meli/connect", follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    assert url.netloc == "auth.mercadolibre.cl"
    return {k: v[0] for k, v in parse_qs(url.query).items()}


def test_conectar_canjea_el_codigo_con_pkce(token_api):
    calls, replies = token_api
    admin = logged_in("admin", role="admin")
    q = connect(admin)
    assert q["client_id"] == "123" and q["code_challenge_method"] == "S256"

    replies.append(granted())
    r = admin.get(
        f"/api/admin/meli/callback?code=TG-code&state={q['state']}", follow_redirects=False
    )
    assert r.status_code == 302 and r.headers["location"].endswith("/admin/tiendas?meli=ok")
    sent = calls[0]
    assert sent["grant_type"] == "authorization_code" and sent["code"] == "TG-code"
    # El verifier enviado corresponde al challenge de la URL de autorización.
    digest = hashlib.sha256(sent["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == q["code_challenge"]

    st = admin.get("/api/admin/meli").json()
    assert st["connected"] and st["can_refresh"] and st["account_id"] == "42"
    assert "access_token" not in st and "refresh_token" not in st


def test_state_invalido_no_canjea(token_api):
    calls, _ = token_api
    admin = logged_in("admin", role="admin")
    connect(admin)
    r = admin.get("/api/admin/meli/callback?code=x&state=otro", follow_redirects=False)
    assert "meli=error" in r.headers["location"]
    assert calls == []


def test_el_state_es_de_un_solo_uso(token_api):
    _, replies = token_api
    admin = logged_in("admin", role="admin")
    q = connect(admin)
    replies.append(granted())
    admin.get(f"/api/admin/meli/callback?code=a&state={q['state']}", follow_redirects=False)
    r = admin.get(f"/api/admin/meli/callback?code=b&state={q['state']}", follow_redirects=False)
    assert "meli=error" in r.headers["location"]


def test_solo_admin(token_api):
    ana = logged_in("ana")
    assert ana.get("/api/admin/meli/connect", follow_redirects=False).status_code == 403
    assert ana.get("/api/admin/meli").status_code == 403


def test_sin_credenciales_no_conecta(monkeypatch):
    monkeypatch.setattr(settings, "meli_client_secret", "")
    admin = logged_in("admin", role="admin")
    assert admin.get("/api/admin/meli/connect", follow_redirects=False).status_code == 503


def guardar_token(expira_en: timedelta, refresh="TG-viejo"):
    with SessionLocal() as db:
        db.merge(
            OAuthToken(
                provider=meli.PROVIDER,
                access_token="APP_USR-viejo",
                refresh_token=refresh,
                expires_at=utcnow() + expira_en,
                account_id="42",
                scope="offline_access read",
            )
        )
        db.commit()


async def test_token_vigente_no_se_renueva(token_api):
    calls, _ = token_api
    guardar_token(timedelta(hours=3))
    assert await meli.access_token() == "APP_USR-viejo"
    assert calls == []


async def test_renueva_una_sola_vez_aunque_pidan_en_paralelo(token_api):
    calls, replies = token_api
    guardar_token(timedelta(minutes=2))
    replies.append(granted(access="APP_USR-nuevo", refresh="TG-nuevo"))
    tokens = await asyncio.gather(*(meli.access_token() for _ in range(5)))
    assert tokens == ["APP_USR-nuevo"] * 5
    assert len(calls) == 1 and calls[0]["refresh_token"] == "TG-viejo"
    with SessionLocal() as db:
        assert db.get(OAuthToken, meli.PROVIDER).refresh_token == "TG-nuevo"


async def test_refresh_invalido_pide_reconectar(token_api):
    _, replies = token_api
    guardar_token(timedelta(minutes=-5))
    replies.append((400, {"error": "invalid_grant", "message": "Error validating grant"}))
    with pytest.raises(meli.NotConnectedError, match="reconectar"):
        await meli.access_token()


async def test_sin_conexion(token_api):
    with pytest.raises(meli.NotConnectedError):
        await meli.access_token()
