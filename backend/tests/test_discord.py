"""Discord por webhook, con transporte HTTP simulado (sin red)."""

import json

import httpx
import pytest
from sqlalchemy import select

from tests.test_api import STARDEW, logged_in, sin_red  # noqa: F401
from tracker.checker import apply_result
from tracker.db import SessionLocal
from tracker.models import Notification, Product
from tracker.notifications import discord
from tracker.processors import ScrapeResult

HOOK = "https://discord.com/api/webhooks/123456789012/abcDEF-_token"


@pytest.fixture
def posted(monkeypatch):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((str(request.url), json.loads(request.content)))
        return httpx.Response(204)

    monkeypatch.setattr(discord, "_transport", httpx.MockTransport(handler))
    return sent


def test_to_markdown():
    assert discord.to_markdown("<b>Juego &amp; más</b>\n• Bajó") == "**Juego & más**\n• Bajó"


def test_valida_y_enmascara_el_webhook(posted):
    api = logged_in("ana")
    r = api.post("/api/channels/discord", {"webhook_url": "https://example.com/hook"})
    assert r.status_code == 422
    r = api.post("/api/channels/discord", {"webhook_url": HOOK})
    assert r.status_code == 201
    assert posted[0][0] == HOOK
    me = api.get("/api/auth/me").json()["discord"]
    assert me["linked"] and me["enabled"]
    assert "abcDEF" not in json.dumps(me)  # el token del webhook no sale a la UI


async def test_alerta_llega_por_discord_y_se_puede_apagar_por_watch(posted):
    api = logged_in("ana")
    api.post("/api/channels/discord", {"webhook_url": HOOK})
    w = api.post(
        "/api/watches",
        {"urls": [STARDEW], "rules": [{"kind": "TARGET_PRICE", "params": {"value": 5000}}]},
    ).json()[0]
    assert w["channels"] == {"discord": True}

    with SessionLocal() as db:
        product = db.get(Product, w["product"]["id"])
        await apply_result(db, product, ScrapeResult("Stardew Valley", 4990, 7500, "CLP", True))
        notif = db.scalar(select(Notification))
        assert list(notif.delivery.values()) == ["ok"]
    content = posted[-1][1]["content"]
    assert "**Stardew Valley**" in content and "$4.990" in content

    r = api.patch(f"/api/watches/{w['id']}", {"channels": {"discord": False}})
    assert r.json()["channels"] == {"discord": False}
    before = len(posted)
    api.patch(
        f"/api/watches/{w['id']}",
        {"rules": [{"kind": "PRICE_DROP", "params": {"min_pct": 1}}]},
    )
    with SessionLocal() as db:
        product = db.get(Product, w["product"]["id"])
        await apply_result(db, product, ScrapeResult("Stardew Valley", 4000, 7500, "CLP", True))
        assert db.scalars(select(Notification)).all()[-1].delivery == {}
    assert len(posted) == before


def test_prueba_de_canal(posted):
    api = logged_in("ana")
    ch = api.post("/api/channels/discord", {"webhook_url": HOOK}).json()
    assert api.post(f"/api/channels/{ch['id']}/test").json() == {"ok": True}
