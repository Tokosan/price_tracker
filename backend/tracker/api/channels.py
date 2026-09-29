"""Canales de notificación del usuario (por ahora, Telegram)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from tracker.api.deps import current_user
from tracker.db import get_db
from tracker.models import Channel, User
from tracker.notifications import discord, telegram
from tracker.notifications.notifier import send_to_channels

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _own_channel(db: DbSession, user: User, channel_id: int) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.user_id != user.id:
        raise HTTPException(404, "no existe")
    return ch


@router.post("/telegram/link")
async def telegram_link(user: User = Depends(current_user)) -> dict:
    """Genera el deep link t.me/<bot>?start=<código de un solo uso> (15 min)."""
    bot = telegram.bot
    if bot is None:
        raise HTTPException(503, "Telegram no configurado en el servidor.")
    if bot.username is None:
        try:
            await bot.get_me()
        except telegram.TelegramError as exc:
            raise HTTPException(503, f"El bot de Telegram no responde: {exc}") from exc
    code = telegram.create_link_code(user.id)
    return {
        "url": f"https://t.me/{bot.username}?start={code}",
        "expires_in_minutes": telegram.LINK_CODE_MINUTES,
    }


class ChannelPatchIn(BaseModel):
    enabled: bool


@router.patch("/{channel_id}")
def update_channel(
    channel_id: int,
    body: ChannelPatchIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict:
    ch = _own_channel(db, user, channel_id)
    ch.enabled = body.enabled
    db.commit()
    return {"id": ch.id, "enabled": ch.enabled}


@router.delete("/{channel_id}", status_code=204)
def delete_channel(
    channel_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> None:
    db.delete(_own_channel(db, user, channel_id))
    db.commit()


class DiscordIn(BaseModel):
    webhook_url: str


@router.post("/discord", status_code=201)
async def discord_connect(
    body: DiscordIn, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    """Guarda (o reemplaza) el webhook de Discord del usuario y manda un mensaje de prueba."""
    url = body.webhook_url.strip()
    if not discord.valid_webhook(url):
        raise HTTPException(
            422, "Eso no parece un webhook de Discord (https://discord.com/api/webhooks/…)."
        )
    try:
        await discord.send(url, "🔔 Webhook conectado al tracker de precios.")
    except discord.DiscordError as exc:
        raise HTTPException(502, f"Discord rechazó el webhook: {exc}") from exc
    ch = db.scalar(select(Channel).where(Channel.user_id == user.id, Channel.kind == "discord"))
    if ch is None:
        ch = Channel(user_id=user.id, kind="discord", config={"webhook_url": url}, enabled=True)
        db.add(ch)
    else:
        ch.config = {"webhook_url": url}
        ch.enabled = True
    db.commit()
    return {"id": ch.id, "enabled": ch.enabled}


@router.post("/{channel_id}/test")
async def channel_test(
    channel_id: int, user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    ch = _own_channel(db, user, channel_id)
    delivery = await send_to_channels([ch], "🔔 Mensaje de prueba del tracker de precios.")
    result = next(iter(delivery.values()))
    if result != "ok":
        raise HTTPException(502, result)
    return {"ok": True}


@router.post("/telegram/test")
async def telegram_test(
    user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict:
    ch = db.scalar(select(Channel).where(Channel.user_id == user.id, Channel.kind == "telegram"))
    if ch is None or telegram.bot is None:
        raise HTTPException(409, "Telegram no está vinculado.")
    try:
        await telegram.bot.send_message(
            ch.config["chat_id"], "🔔 Mensaje de prueba del tracker de precios."
        )
    except telegram.TelegramError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True}
