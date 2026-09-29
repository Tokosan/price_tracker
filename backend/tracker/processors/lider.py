"""Procesador de Lider Supermercado (super.lider.cl, plataforma de Walmart).

La ficha es una página Next.js: el producto viene completo en `__NEXT_DATA__`
(`props.pageProps.initialData.data.product`), con precio, precio "antes" y stock.
El JSON-LD `Product` sirve de respaldo. El sitio tiene PerimeterX: con un
User-Agent de navegador las fichas responden, pero si nos marca redirige a
`/blocked` ("Robot or human?") con HTTP 200, que se trata como error de lectura.
"""

import json
import re
from datetime import timedelta

from tracker.processors.base import FetchError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.util import availability_in_stock, find_ld_product, first_offer, to_minor

# /ip/<categoría>/<id> o /ip/<id>; la categoría no importa (cualquiera sirve).
_URL_RE = re.compile(
    r"^https?://super\.lider\.cl/ip/(?:[a-z0-9-]+/)?(\d{6,20})/?(?:[?#].*)?$", re.I
)
_NEXT_RE = re.compile(
    r"<script[^>]*\bid=[\"']?__NEXT_DATA__[\"']?[^>]*>(.*?)</script>", re.S | re.I
)
_BLOCKED_RE = re.compile(r"<title>\s*Robot or human\?", re.I)


class LiderProcessor(Processor):
    name = "lider"
    label = "Lider"
    check_interval = timedelta(hours=6)
    home_url = "https://super.lider.cl/"
    example_url = "https://super.lider.cl/ip/cereales/00780242000793"
    platform = "Walmart"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Solo el supermercado (super.lider.cl/ip/…). Precio de la tienda por defecto "
        "del sitio (retiro en Vitacura); los productos a granel se siguen por kilo."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de Lider")
        item_id = m.group(1)
        return ProductRef(item_id, f"https://super.lider.cl/ip/{item_id}")

    def domain(self) -> str:
        return "super.lider.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        if _BLOCKED_RE.search(raw):
            raise FetchError("Lider bloqueó la lectura (captcha de PerimeterX)")
        product = _next_product(raw)
        if product:
            return _from_next(product)
        return _from_ld(raw)


def _next_product(raw: str) -> dict | None:
    m = _NEXT_RE.search(raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    product = (
        data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {})
    ).get("product")
    return product if isinstance(product, dict) and product.get("usItemId") else None


def _from_next(product: dict) -> ScrapeResult:
    info = product.get("priceInfo") or {}
    current = info.get("currentPrice") or {}
    currency = current.get("currencyUnit") or "CLP"
    price = to_minor(current.get("price"), currency)
    was = to_minor((info.get("wasPrice") or {}).get("price"), currency)
    title = (product.get("name") or "").strip()
    if product.get("salesUnit") == "WEIGHT" and title:
        title += " (por kg)"  # el precio que muestra es por kilo
    images = product.get("imageInfo") or {}
    return ScrapeResult(
        title=title,
        price=price,
        list_price=was if was and price is not None and was > price else None,
        currency=currency,
        available=product.get("availabilityStatus") == "IN_STOCK",
        image_url=images.get("thumbnailUrl"),
    )


def _from_ld(raw: str) -> ScrapeResult:
    product = find_ld_product(raw)
    if not product:
        return ScrapeResult("", None, None, "CLP", False, None)
    offer = first_offer(product) or {}
    currency = offer.get("priceCurrency") or "CLP"
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    return ScrapeResult(
        title=(product.get("name") or "").strip(),
        price=to_minor(offer.get("price"), currency),
        list_price=None,
        currency=currency,
        available=availability_in_stock(offer.get("availability")),
        image_url=image if isinstance(image, str) else None,
    )
