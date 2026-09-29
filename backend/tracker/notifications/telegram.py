"""Bot de Telegram con long polling (getUpdates). No se expone ningún webhook."""

import asyncio
import logging
from datetime import timedelta

import httpx
from sqlalchemy import select

from tracker.config import settings
from tracker.db import SessionLocal, utcnow
from tracker.models import Channel, TelegramLinkCode
from tracker.security import new_token, token_hash

log = logging.getLogger("tracker.telegram")

LINK_CODE_MINUTES = 15

# Los tests lo reemplazan por un httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None


class TelegramError(Exception):
    pass


class TelegramBot:
    def __init__(self, token: str):
        self._token = token
        self.username: str | None = None
        self.last_error: str | None = None
        self.polling = False

    @property
    def _base(self) -> str:
        return f"https://api.telegram.org/bot{self._token}"

    async def _call(self, method: str, *, http_timeout: float = 20, **params) -> dict:
        # `http_timeout` es del cliente HTTP; `timeout` (si viene en params) es el
        # del long polling de getUpdates, que Telegram espera en el cuerpo.
        try:
            async with httpx.AsyncClient(timeout=http_timeout, transport=_transport) as client:
                resp = await client.post(f"{self._base}/{method}", json=params)
        except httpx.HTTPError as exc:
            # Sin repr de la URL: lleva el token.
            raise TelegramError(f"{method}: error de red ({type(exc).__name__})") from None
        data = resp.json() if resp.content else {}
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', resp.status_code)}")
        return data["result"]

    async def get_me(self) -> dict:
        me = await self._call("getMe")
        self.username = me.get("username")
        return me

    async def send_message(self, chat_id: int | str, text: str) -> None:
        await self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    async def poll_forever(self) -> None:
        """Bucle de long polling. Se cancela al apagar la app."""
        offset: int | None = None
        backoff = 5
        while True:
            try:
                if self.username is None:
                    await self.get_me()
                    log.info("Telegram: bot @%s listo, empezando long polling", self.username)
                self.polling = True
                params: dict = {"timeout": 30, "allowed_updates": ["message"]}
                if offset is not None:
                    params["offset"] = offset
                updates = await self._call("getUpdates", http_timeout=45, **params)
                self.last_error = None
                backoff = 5
                for upd in updates:
                    offset = upd["update_id"] + 1
                    try:
                        await self._handle(upd)
                    except Exception:
                        log.exception("Telegram: error procesando update %s", upd.get("update_id"))
            except asyncio.CancelledError:
                self.polling = False
                raise
            except Exception as exc:
                self.polling = False
                self.last_error = str(exc)
                log.warning("Telegram: %s (reintento en %ss)", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)

    async def _handle(self, update: dict) -> None:
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None or not text.startswith("/start"):
            if chat_id is not None and msg.get("chat", {}).get("type") == "private":
                await self.send_message(
                    chat_id, "Hola. Vincula este chat desde la app: Ajustes → Conectar Telegram."
                )
            return
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if not code:
            await self.send_message(
                chat_id, "Para vincular, usa el botón «Conectar Telegram» en la app."
            )
            return
        reply = link_chat(code, chat_id, (msg.get("from") or {}).get("username"))
        await self.send_message(chat_id, reply)


def create_link_code(user_id: int) -> str:
    code = new_token()[:24]
    with SessionLocal() as db:
        db.add(
            TelegramLinkCode(
                user_id=user_id,
                code_hash=token_hash(code),
                expires_at=utcnow() + timedelta(minutes=LINK_CODE_MINUTES),
            )
        )
        db.commit()
    return code


def link_chat(code: str, chat_id: int, tg_username: str | None) -> str:
    """Consume un código de vinculación y crea (o actualiza) el canal del usuario."""
    with SessionLocal() as db:
        row = db.scalar(
            select(TelegramLinkCode).where(TelegramLinkCode.code_hash == token_hash(code))
        )
        if row is None or row.used_at is not None or row.expires_at < utcnow():
            return "Este link ya se usó o expiró. Genera uno nuevo desde la app."
        row.used_at = utcnow()
        channel = db.scalar(
            select(Channel).where(Channel.user_id == row.user_id, Channel.kind == "telegram")
        )
        config = {"chat_id": chat_id, "username": tg_username}
        if channel is None:
            db.add(Channel(user_id=row.user_id, kind="telegram", config=config, enabled=True))
        else:
            channel.config = config
            channel.enabled = True
        db.commit()
    return "✅ Listo: este chat recibirá las alertas del tracker de precios."


bot: TelegramBot | None = (
    TelegramBot(settings.telegram_bot_token) if settings.telegram_bot_token else None
)
