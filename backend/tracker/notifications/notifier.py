"""Entrega de notificaciones por los canales del usuario."""

import html
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from tracker.models import Channel, User, Watch, WatchChannel
from tracker.notifications import discord, telegram

log = logging.getLogger("tracker.notifier")


def channels_for_watch(db: DbSession, watch: Watch) -> list[Channel]:
    overrides = {
        wc.channel_id: wc.enabled
        for wc in db.scalars(select(WatchChannel).where(WatchChannel.watch_id == watch.id))
    }
    return [
        ch
        for ch in db.scalars(
            select(Channel).where(Channel.user_id == watch.user_id, Channel.enabled.is_(True))
        )
        if overrides.get(ch.id, True)
    ]


async def send_to_channels(channels: list[Channel], text: str) -> dict:
    delivery: dict[str, str] = {}
    for ch in channels:
        key = f"{ch.kind}:{ch.id}"
        if ch.kind == "telegram":
            if telegram.bot is None:
                delivery[key] = "telegram no configurado"
                continue
            try:
                await telegram.bot.send_message(ch.config["chat_id"], text)
                delivery[key] = "ok"
            except Exception as exc:
                log.warning("Telegram: no se pudo enviar al canal %s: %s", ch.id, exc)
                delivery[key] = f"error: {exc}"
        elif ch.kind == "discord":
            try:
                await discord.send(ch.config["webhook_url"], text)
                delivery[key] = "ok"
            except Exception as exc:
                log.warning("Discord: no se pudo enviar al canal %s: %s", ch.id, exc)
                delivery[key] = f"error: {exc}"
        else:
            delivery[key] = "canal no soportado"
    return delivery


async def notify_admins(db: DbSession, text: str) -> None:
    """Aviso operativo a los admins (p. ej. un producto quedó broken)."""
    channels = list(
        db.scalars(
            select(Channel)
            .join(User, User.id == Channel.user_id)
            .where(User.role == "admin", User.active.is_(True), Channel.enabled.is_(True))
        )
    )
    if channels:
        await send_to_channels(channels, text)


def esc(text: str) -> str:
    return html.escape(text or "", quote=False)
