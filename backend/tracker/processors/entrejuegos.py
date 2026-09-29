"""Procesador de Entrejuegos (PrestaShop detrás de Cloudflare → FlareSolverr)."""

from tracker.processors.base import ProductRef
from tracker.processors.http import flaresolverr_get
from tracker.processors.prestashop import PrestaShopProcessor


class EntrejuegosProcessor(PrestaShopProcessor):
    name = "entrejuegos"
    label = "Entrejuegos"
    host = "entrejuegos.cl"
    canonical_host = "www.entrejuegos.cl"
    home_url = "https://www.entrejuegos.cl/"
    example_url = "https://www.entrejuegos.cl/avanzados/18597-frosthaven.html"
    slow = True
    notes = "Tiene protección anti-bots: la primera lectura puede tardar hasta un minuto."

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await flaresolverr_get(ref.canonical_url)
