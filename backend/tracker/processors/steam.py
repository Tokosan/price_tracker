"""Procesador de Steam (región fija cc=cl)."""

import json
import re
from datetime import timedelta

from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.util import exponent

_APP_RE = re.compile(r"^https?://(?:store\.)?steampowered\.com/(?:agecheck/)?app/(\d+)", re.I)
API_URL = "https://store.steampowered.com/api/appdetails"


def steam_to_minor(amount: int, currency: str) -> int:
    """Steam entrega todos los montos ×100, incluso en monedas sin decimales.

    `final: 750000` con `currency: "CLP"` son $7.500, no $750.000. En USD
    (2 decimales) los centavos ya son la unidad mínima y no hay que dividir.
    """
    return int(amount) // (10 ** (2 - exponent(currency)))


class SteamProcessor(Processor):
    name = "steam"
    label = "Steam"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # La API de Steam es estructurada: las ofertas de −90 % (y los juegos que se
    # regalan a $0) son reales, no errores de scraping.
    anomaly_drop_pct = None
    home_url = "https://store.steampowered.com/"
    example_url = "https://store.steampowered.com/app/413150/Stardew_Valley/"
    platform = "API de Steam"
    notes = "Precios de la tienda de Chile. Las ofertas cambian a las 10:00 hora del Pacífico."

    def matches(self, url: str) -> bool:
        return bool(_APP_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _APP_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de juego de Steam")
        app_id = m.group(1)
        return ProductRef(app_id, f"https://store.steampowered.com/app/{app_id}/")

    def domain(self) -> str:
        return "store.steampowered.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(
            API_URL, params={"appids": ref.external_id, "cc": "cl", "l": "spanish"}
        )

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("la API de Steam no devolvió JSON") from exc
        entry = (body or {}).get(ref.external_id) or {}
        if not entry.get("success"):
            raise NotFoundError(f"Steam no reconoce el app {ref.external_id}")
        data = entry.get("data") or {}
        title = data.get("name") or f"App {ref.external_id}"
        image = data.get("header_image")
        overview = data.get("price_overview")
        if overview:
            currency = overview.get("currency") or "CLP"
            final = steam_to_minor(overview["final"], currency)
            initial = steam_to_minor(overview.get("initial", overview["final"]), currency)
            return ScrapeResult(
                title=title,
                price=final,
                list_price=initial if initial > final else None,
                currency=currency,
                available=True,
                image_url=image,
            )
        if data.get("is_free"):
            return ScrapeResult(title, 0, None, "CLP", True, image)
        # Sin precio y sin ser gratis: por ejemplo, aún no sale a la venta.
        return ScrapeResult(title, None, None, "CLP", False, image)
