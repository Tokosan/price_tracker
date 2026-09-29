"""Bot de Telegram contra un transporte HTTP simulado (sin red)."""

import asyncio
import json

import httpx
from sqlalchemy import select

from tracker.models import Channel, User
from tracker.notifications import telegram


def fake_api(updates):
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        calls.append((method, body))
        if method == "getMe":
            return httpx.Response(
                200, json={"ok": True, "result": {"id": 1, "username": "test_bot"}}
            )
        if method == "getUpdates":
            if not updates:
                # Simula la espera del long polling: cede el event loop.
                await asyncio.sleep(0.05)
            batch = updates.pop(0) if updates else []
            return httpx.Response(200, json={"ok": True, "result": batch})
        return httpx.Response(200, json={"ok": True, "result": {}})

    return httpx.MockTransport(handler), calls


async def test_long_polling_vincula_el_chat_con_el_deep_link(session, monkeypatch):
    user = User(username="ana", role="user", active=True)
    session.add(user)
    session.commit()
    code = telegram.create_link_code(user.id)
    updates = [
        [
            {
                "update_id": 7,
                "message": {
                    "text": f"/start {code}",
                    "chat": {"id": 555, "type": "private"},
                    "from": {"username": "ana_tg"},
                },
            }
        ]
    ]
    transport, calls = fake_api(updates)
    monkeypatch.setattr(telegram, "_transport", transport)

    bot = telegram.TelegramBot("123:abc")
    task = asyncio.create_task(bot.poll_forever())
    for _ in range(50):
        await asyncio.sleep(0.01)
        if any(m == "sendMessage" for m, _ in calls):
            break
    task.cancel()

    assert bot.username == "test_bot"
    polls = [b for m, b in calls if m == "getUpdates"]
    assert polls[0]["timeout"] == 30  # long polling
    assert polls[1]["offset"] == 8  # confirma el update procesado
    ch = session.scalar(select(Channel).where(Channel.user_id == user.id))
    assert ch.kind == "telegram" and ch.config["chat_id"] == 555
    # El código es de un solo uso.
    assert "ya se usó" in telegram.link_chat(code, 999, None)
