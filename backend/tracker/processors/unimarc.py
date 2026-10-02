"""Procesador de Unimarc (supermercado de SMU; front Next.js sobre VTEX).

El sitio está detrás de Akamai: con el cliente HTTP/1.1 de siempre responde 403, pero pasa
con HTTP/2 y headers completos de navegador. Fuentes, en orden:

1. El BFF del front (`bff-unimarc-ecommerce.unimarc.cl/catalog/product/search/by-slug/<slug>`,
   con los headers `channel`, `source` y `version`): JSON chico con precio, precio "antes" y
   stock (`price.availableQuantity`). Si el producto no existe responde 500, no 404.
2. Si el BFF falla, la ficha HTML: un 404 es la única señal de producto inexistente, y con
   200 el mismo producto viene en `__NEXT_DATA__` (`props.pageProps.product`).
3. Si Akamai bloquea las dos, la API pública de VTEX por slug (sin WAF). Es solo un respaldo:
   con `[]` no se sabe si el producto se borró o está oculto, así que es error de lectura.

El precio "Club Unimarc" (programa gratuito, no una tarjeta) es el precio que ve cualquiera
y se toma. Las promociones "lleva X" (`promotion.price`) se ignoran.
"""

import json
import re
from datetime import timedelta

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
)
from tracker.processors.http import get_text
from tracker.processors.util import digits_to_int
from tracker.processors.vtex import VtexProcessor

_URL_RE = re.compile(r"^https?://(?:www\.)?unimarc\.cl/product/([a-z0-9-]+)/?(?:[?#].*)?$", re.I)
_NEXT_RE = re.compile(
    r"<script[^>]*\bid=[\"']?__NEXT_DATA__[\"']?[^>]*>(.*?)</script>", re.S | re.I
)
BFF_URL = "https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search/by-slug/{slug}"
# Lo que manda el front al BFF (una petición fetch, no una navegación).
BFF_HEADERS = {
    "Accept": "application/json",
    "channel": "UNIMARC",
    "source": "web",
    "version": "1.0.0",
    "Origin": "https://www.unimarc.cl",
    "Referer": "https://www.unimarc.cl/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


class _UnimarcVtex(VtexProcessor):
    """Solo para leer el respaldo VTEX (no se registra)."""

    name = "unimarc-vtex"
    label = "Unimarc"
    host = "www.unimarc.cl"
    account = "unimarc"

    def search_url(self, slug: str) -> str:
        return super().search_url(slug) + "?sc=39"  # canal de venta de unimarc.cl


_vtex = _UnimarcVtex()


class UnimarcProcessor(Processor):
    name = "unimarc"
    label = "Unimarc"
    check_interval = timedelta(hours=12)
    fixture_ext = "json"  # el BFF; el respaldo HTML se guarda tal cual (empieza con "<")
    home_url = "https://www.unimarc.cl/"
    example_url = "https://www.unimarc.cl/product/arroz-basmati-miraflores-400-gr"
    platform = "Next.js + VTEX (BFF propio)"
    supports_list_price = True
    notes = (
        "Incluye el precio Club Unimarc (gratis, lo ve cualquiera); las promociones "
        "“lleva X” no se consideran. Detrás de Akamai: si bloquea, se lee la API de VTEX."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de Unimarc")
        slug = m.group(1).lower()
        return ProductRef(slug, f"https://www.unimarc.cl/product/{slug}")

    def domain(self) -> str:
        return "www.unimarc.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        slug = ref.external_id
        try:
            raw = await get_text(
                BFF_URL.format(slug=slug), http2=True, browser_headers=True, headers=BFF_HEADERS
            )
            if _bff_product(raw):
                return raw
        except FetchError:  # 500 si no existe, 403 si Akamai bloquea: no es concluyente
            pass
        try:
            return await get_text(ref.canonical_url, http2=True, browser_headers=True)
        except NotFoundError:
            raise
        except FetchError:
            pass
        return await get_text(_vtex.search_url(slug))

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        text = raw.lstrip()
        if text.startswith("<"):
            product = _next_product(text)
            if product is None:
                raise FetchError("la página de Unimarc no trae el producto")
            return _from_bff(product)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise FetchError("Unimarc no devolvió JSON") from exc
        if isinstance(data, list):
            if not data:
                # VTEX oculta productos (sin stock en el canal, despublicados): no basta
                # para decir que no existe.
                raise FetchError("el respaldo VTEX no trae el producto")
            return _vtex.parse(text, ProductRef(ref.external_id, ref.canonical_url))
        product = _bff_product(text)
        if product is None:
            raise FetchError("el BFF de Unimarc no trae el producto")
        return _from_bff(product)


def _first_product(container) -> dict | None:
    products = container.get("products") if isinstance(container, dict) else None
    if isinstance(products, list) and products and isinstance(products[0], dict):
        return products[0]
    return None


def _bff_product(raw: str) -> dict | None:
    try:
        return _first_product(json.loads(raw))
    except ValueError:
        return None


def _next_product(html: str) -> dict | None:
    m = _NEXT_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    page = (data.get("props") or {}).get("pageProps") or {}
    return _first_product(page.get("product"))


def _from_bff(product: dict) -> ScrapeResult:
    info = product.get("price")
    item = product.get("item") or {}
    if not isinstance(info, dict):
        raise FetchError("el producto de Unimarc no trae precio")
    price = digits_to_int(str(info.get("price") or ""))
    quantity = info.get("availableQuantity")
    if not price or not isinstance(quantity, int | float):
        # Sin precio o sin cantidad no hay lectura confiable (y "sin stock" avisaría).
        raise FetchError("el precio o el stock de Unimarc viene incompleto")
    listed = digits_to_int(str(info.get("listPrice") or ""))
    images = item.get("images") or []
    return ScrapeResult(
        title=(item.get("nameComplete") or item.get("name") or "").strip(),
        price=price,
        list_price=listed if listed and listed > price else None,
        currency="CLP",
        available=quantity > 0,
        image_url=images[0] if images and isinstance(images[0], str) else None,
    )
