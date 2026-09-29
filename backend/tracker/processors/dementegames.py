"""Procesador de DementeGames (PrestaShop 1.7; Cloudflare sin challenge → httpx directo)."""

from tracker.processors.base import ProductRef
from tracker.processors.http import get_text
from tracker.processors.prestashop import PrestaShopProcessor


class DementeGamesProcessor(PrestaShopProcessor):
    name = "dementegames"
    label = "DementeGames"
    host = "dementegames.cl"
    canonical_host = "dementegames.cl"
    home_url = "https://dementegames.cl/"
    example_url = "https://dementegames.cl/tematicos/189-gloomhaven.html"
    notes = "Las preventas con unidades disponibles cuentan como en stock."

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)
