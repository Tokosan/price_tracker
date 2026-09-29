"""Discord por webhook: cada usuario pega la URL del webhook de su canal."""

import html
import re

import httpx

WEBHOOK_RE = re.compile(
    r"^https://(?:ptb\.|canary\.)?(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$"
)

# Los tests lo reemplazan por un httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None


class DiscordError(Exception):
    pass


def valid_webhook(url: str) -> bool:
    return bool(WEBHOOK_RE.match(url.strip()))


def mask_webhook(url: str) -> str:
    """La URL del webhook es un secreto: a la UI solo va el id del webhook."""
    m = re.search(r"/webhooks/(\d+)/", url)
    return f"webhook …{m.group(1)[-6:]}" if m else "webhook"


def to_markdown(text: str) -> str:
    """El mensaje se arma en el HTML simple de Telegram; Discord usa Markdown."""
    text = re.sub(r"</?b>", "**", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def send(webhook_url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15, transport=_transport) as client:
            resp = await client.post(
                webhook_url,
                json={"content": to_markdown(text)[:2000], "allowed_mentions": {"parse": []}},
            )
    except httpx.HTTPError as exc:
        # Sin la URL en el mensaje: lleva el token del webhook.
        raise DiscordError(f"error de red ({type(exc).__name__})") from None
    if resp.status_code >= 300:
        raise DiscordError(f"HTTP {resp.status_code}")
