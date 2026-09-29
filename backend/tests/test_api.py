"""API de punta a punta con TestClient (procesadores con fixtures, sin red)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import fixture_text
from tracker.config import settings
from tracker.db import SessionLocal
from tracker.main import app
from tracker.models import PricePoint, Product, SiteRequest, User
from tracker.processors import PROCESSORS
from tracker.security import create_invite

STARDEW = "https://store.steampowered.com/app/413150/Stardew_Valley/"
BILLY = "https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/"
PASSWORD = "una-clave-larga-123"


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    settings.domain_min_interval = 0
    fixtures = {
        "413150": ("steam", "stardew_valley.json"),
        "00263850": ("ikea", "billy_blanco.html"),
        "50508652": ("ikea", "billy_blanco.html"),  # basta para tener precio
    }

    def fake(proc):
        async def fetch_raw(ref):
            processor, name = fixtures[ref.external_id]
            return fixture_text(processor, name)

        return fetch_raw

    for proc in PROCESSORS.values():
        monkeypatch.setattr(proc, "fetch_raw", fake(proc))


class Api:
    def __init__(self):
        self.c = TestClient(app, base_url="https://testserver")
        self.c.get("/api/auth/csrf")

    def _h(self):
        return {"X-CSRF-Token": self.c.cookies.get("tracker_csrf", "")}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None):
        return self.c.post(url, json=json, headers=self._h())

    def patch(self, url, json=None):
        return self.c.patch(url, json=json, headers=self._h())

    def delete(self, url):
        return self.c.delete(url, headers=self._h())


def make_user(username, role="user") -> str:
    with SessionLocal() as db:
        user = User(username=username, role=role, active=True)
        db.add(user)
        db.flush()
        link = create_invite(db, user)
        db.commit()
    return link.rsplit("/", 1)[-1]


def logged_in(username, role="user") -> Api:
    api = Api()
    token = make_user(username, role)
    r = api.post(f"/api/auth/invite/{token}", {"password": PASSWORD})
    assert r.status_code == 200, r.text
    return api


def test_health():
    r = Api().get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["db_journal_mode"] == "wal"
    assert r.json()["telegram"] == {"configured": False}


def test_invitacion_de_un_solo_uso_y_login():
    api = Api()
    token = make_user("ana")
    assert api.get(f"/api/auth/invite/{token}").json()["username"] == "ana"
    assert api.post(f"/api/auth/invite/{token}", {"password": "corta"}).status_code == 422
    assert api.post(f"/api/auth/invite/{token}", {"password": PASSWORD}).status_code == 200
    # Ya se usó.
    assert api.post(f"/api/auth/invite/{token}", {"password": PASSWORD}).status_code == 404
    assert api.get("/api/auth/me").json()["username"] == "ana"

    other = Api()
    assert other.post("/api/auth/login", {"username": "ana", "password": "mala"}).status_code == 401
    r = other.post("/api/auth/login", {"username": "ana", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert other.get("/api/auth/me").status_code == 200
    assert other.post("/api/auth/logout").status_code == 200
    assert other.get("/api/auth/me").status_code == 401


def test_sin_sesion_401():
    assert Api().get("/api/watches").status_code == 401


def test_csrf_obligatorio():
    api = logged_in("ana")
    r = api.c.post("/api/resolve", json={"url": STARDEW})  # sin header
    assert r.status_code == 403
    r = api.c.post("/api/resolve", json={"url": STARDEW}, headers={"X-CSRF-Token": "otro"})
    assert r.status_code == 403


def test_url_sin_procesador_se_rechaza_y_se_puede_reportar():
    api = logged_in("ana")
    r = api.post("/api/resolve", {"url": "https://www.falabella.com/falabella-cl/product/123"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "unsupported"
    r = api.post("/api/site-requests", {"url": "https://www.falabella.com/x", "note": "porfa"})
    assert r.status_code == 201
    with SessionLocal() as db:
        assert db.scalar(select(SiteRequest.note)) == "porfa"


def test_agregar_ikea_con_variantes_y_reglas():
    api = logged_in("ana")
    r = api.post("/api/resolve", {"url": BILLY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product"]["current"]["price"] == 59990
    assert {v["external_id"] for v in body["variants"]} == {"00263850", "50508652", "10508932"}

    urls = [v["url"] for v in body["variants"] if v["external_id"] in ("00263850", "50508652")]
    rules = [
        {"kind": "TARGET_PRICE", "params": {"value": 50000}},
        {"kind": "DISCOUNT_PCT", "params": {"pct": 15, "baseline": "watch_start"}},
        {"kind": "BACK_IN_STOCK", "params": {}},
    ]
    r = api.post("/api/watches", {"urls": urls, "rules": rules})
    assert r.status_code == 201, r.text
    watches = r.json()
    assert len(watches) == 2
    assert all(w["price_at_start"] == 59990 for w in watches)
    assert [x["kind"] for x in watches[0]["rules"]] == [
        "TARGET_PRICE",
        "DISCOUNT_PCT",
        "BACK_IN_STOCK",
    ]
    assert len(api.get("/api/watches").json()) == 2
    # Volver a agregar el mismo no duplica.
    api.post("/api/watches", {"urls": urls[:1], "rules": []})
    assert len(api.get("/api/watches").json()) == 2


def test_regla_invalida_422():
    api = logged_in("ana")
    r = api.post(
        "/api/watches",
        {"urls": [STARDEW], "rules": [{"kind": "TARGET_PRICE", "params": {"value": -1}}]},
    )
    assert r.status_code == 422


def test_privacidad_entre_usuarios():
    ana = logged_in("ana")
    wid = ana.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]["id"]
    beto = logged_in("beto")
    assert beto.get("/api/watches").json() == []
    assert beto.get(f"/api/watches/{wid}").status_code == 404
    assert beto.patch(f"/api/watches/{wid}", {"active": False}).status_code == 404
    assert beto.delete(f"/api/watches/{wid}").status_code == 404
    assert beto.get(f"/api/watches/{wid}/history").status_code == 404
    assert beto.get("/api/admin/metrics").status_code == 403


def test_revisar_ahora_con_cooldown():
    api = logged_in("ana")
    wid = api.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]["id"]
    r = api.post(f"/api/watches/{wid}/check")
    assert r.status_code == 200, r.text
    assert r.json()["outcome"]["ok"] is True
    assert r.json()["watch"]["product"]["manual_check_available_at"] is not None
    r = api.post(f"/api/watches/{wid}/check")
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "cooldown"
    hist = api.get(f"/api/watches/{wid}/history").json()
    assert [p["price"] for p in hist] == [7500, 7500]


def test_editar_reglas_y_pausar():
    api = logged_in("ana")
    w = api.post(
        "/api/watches",
        {"urls": [STARDEW], "rules": [{"kind": "PRICE_DROP", "params": {"min_pct": 10}}]},
    ).json()[0]
    rid = w["rules"][0]["id"]
    r = api.patch(
        f"/api/watches/{w['id']}",
        {
            "active": False,
            "rules": [
                {"id": rid, "kind": "PRICE_DROP", "params": {"min_pct": 10}},
                {"kind": "PRICE_UP", "params": {"min_pct": 5}},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["rules"][0]["id"] == rid
    assert [x["kind"] for x in body["rules"]] == ["PRICE_DROP", "PRICE_UP"]


def test_cuota_de_watches():
    api = logged_in("ana")
    with SessionLocal() as db:
        db.scalar(select(User).where(User.username == "ana")).watch_quota = 1
        db.commit()
    assert api.post("/api/watches", {"urls": [STARDEW], "rules": []}).status_code == 201
    assert api.post("/api/watches", {"urls": [BILLY], "rules": []}).status_code == 409


def test_admin_invita_desactiva_y_ve_metricas():
    admin = logged_in("jefe", role="admin")
    r = admin.post("/api/admin/users", {"username": "Carla"})
    assert r.status_code == 201
    assert "/invite/" in r.json()["invite_url"]
    carla_id = r.json()["user"]["id"]
    token = r.json()["invite_url"].rsplit("/", 1)[-1]

    carla = Api()
    assert carla.post(f"/api/auth/invite/{token}", {"password": PASSWORD}).status_code == 200
    carla.post("/api/watches", {"urls": [STARDEW], "rules": []})

    m = admin.get("/api/admin/metrics").json()
    assert m["users"] == 2 and m["watches"] == 1
    # Las métricas no dicen qué sigue cada uno.
    assert "413150" not in str(m)

    assert admin.patch(f"/api/admin/users/{carla_id}", {"active": False}).status_code == 200
    assert carla.get("/api/auth/me").status_code == 401  # sesión revocada al instante
    assert (
        admin.patch(f"/api/admin/users/{carla_id}", {"watch_quota": 5}).json()["watch_quota"] == 5
    )


def test_telegram_no_configurado():
    api = logged_in("ana")
    assert api.get("/api/auth/me").json()["telegram"]["configured"] is False
    assert api.post("/api/channels/telegram/link").status_code == 503


def test_historial_de_precios_compartido_entre_usuarios():
    ana = logged_in("ana")
    ana.post("/api/watches", {"urls": [STARDEW], "rules": []})
    beto = logged_in("beto")
    w = beto.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    # Beto hereda el historial ya leído del mismo Product.
    assert len(beto.get(f"/api/watches/{w['id']}/history").json()) >= 1
    with SessionLocal() as db:
        assert len(db.scalars(select(PricePoint)).all()) == 1


def test_cli_borra_usuario_y_productos_huerfanos(monkeypatch, capsys):
    import sys

    from tracker import cli
    from tracker.models import Anomaly, Product

    ana = logged_in("ana")
    ana.post("/api/watches", {"urls": [STARDEW, BILLY], "rules": []})
    beto = logged_in("beto")
    beto.post("/api/watches", {"urls": [STARDEW], "rules": []})
    monkeypatch.setattr(sys, "argv", ["cli", "delete-user", "ana", "--purge-orphan-products"])
    cli.main()
    with SessionLocal() as db:
        # BILLY solo lo seguía ana: se borra con su historial; Stardew lo sigue beto.
        assert [p.external_id for p in db.scalars(select(Product))] == ["413150"]
        assert db.scalars(select(Anomaly)).all() == []
        assert db.scalar(select(User).where(User.username == "ana")) is None
    assert "1 producto(s)" in capsys.readouterr().out


def test_sitios_soportados_con_mis_productos_y_estado_agregado():
    ana, bob = logged_in("ana"), logged_in("bob")
    ana.post("/api/watches", {"urls": [STARDEW], "rules": []})

    sites = {s["name"]: s for s in ana.get("/api/processors").json()}
    assert set(sites) == set(PROCESSORS)
    steam = sites["steam"]
    assert (steam["my_watches"], steam["status"]) == (1, "ok")
    assert steam["last_ok_at"] and steam["example_url"] and steam["domain"]
    assert sites["ikea"]["supports_variants"] and not sites["ikea"]["supports_list_price"]
    assert sites["entrejuegos"]["slow"]
    assert sites["dementegames"]["status"] == "unknown"

    # Bob ve el estado del sitio, pero no cuántos productos sigue Ana.
    assert {s["name"]: s["my_watches"] for s in bob.get("/api/processors").json()}["steam"] == 0

    with SessionLocal() as db:
        db.scalars(select(Product).where(Product.processor == "steam")).one().status = "broken"
        db.commit()
    steam = {s["name"]: s for s in bob.get("/api/processors").json()}["steam"]
    assert steam["status"] == "problems"


def test_preferencias_de_tema_por_usuario():
    ana, bob = logged_in("ana"), logged_in("bob")
    assert ana.get("/api/auth/me").json()["preferences"] == {"theme": "system", "palette": "green"}
    r = ana.patch("/api/auth/preferences", {"theme": "light"})
    assert r.json() == {"theme": "light", "palette": "green"}
    r = ana.patch("/api/auth/preferences", {"palette": "blue"})
    assert r.json() == {"theme": "light", "palette": "blue"}
    assert ana.get("/api/auth/me").json()["preferences"] == {"theme": "light", "palette": "blue"}
    # Son de cada usuario.
    assert bob.get("/api/auth/me").json()["preferences"]["theme"] == "system"
    assert ana.patch("/api/auth/preferences", {"theme": "neon"}).status_code == 422
