"""Base para tiendas VTEX (Jumbo, …), vía la API pública del catálogo.

`GET https://<cuenta>.vtexcommercestable.com.br/api/catalog_system/pub/products/search/<slug>/p`
responde sin clave ni cookies con una lista: `[]` si el slug no existe, o el producto con
sus `items` (SKU) y, por cada vendedor, la oferta (`commertialOffer`) con precio, precio
"antes" y stock. El HTML de la ficha sirve peor: Jumbo responde 404 en un agotado con
precio 0, mientras que la API sí lo lista.

Cada tienda solo define su `host` y su `account`. Si sus items son variantes elegibles
(p. ej. colores que comparten la URL), activa `supports_variants` y redefine `item_label`:
`variant_id` es el `itemId`.
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
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import to_minor


class VtexProcessor(Processor):
    """Subclases: `name`, `label`, `host` (con www), `account` y los metadatos."""

    host: str = ""
    account: str = ""
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # API no oficial: se mantiene el control de caídas. Con precio 0 y sin stock la
    # tienda no tiene precio que mostrar: es un agotado real, no un parseo roto.
    sold_out_without_price = True
    platform = "VTEX"

    def __init__(self) -> None:
        bare = self.host.removeprefix("www.")
        # Ficha: /<slug>/p. Categorías (/despensa/conservas) y búsquedas no matchean.
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(bare)}/([a-z0-9-]+)/p/?(?:[?#].*)?$", re.I
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = self._url_re.match(url.strip())
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        slug = m.group(1).lower()
        return ProductRef(slug, f"https://{self.host}/{slug}/p")

    def domain(self) -> str:
        return f"{self.account}.vtexcommercestable.com.br"

    def search_url(self, slug: str) -> str:
        return f"https://{self.domain()}/api/catalog_system/pub/products/search/{slug}/p"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(self.search_url(ref.external_id))

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = _product(raw, ref)
        item = _item(product, ref)
        offer = _offer(item)
        price = to_minor(offer.get("Price"), "CLP")
        if price is None or not isinstance(offer.get("IsAvailable"), bool):
            raise FetchError("la oferta de VTEX no trae Price o IsAvailable")
        available = offer["IsAvailable"] and (offer.get("AvailableQuantity") or 0) > 0
        if price == 0:
            # Sin stock, precio 0 es un agotado real (sold_out_without_price). Con stock
            # queda price=None, que el checker trata como anomalía.
            price = None
        listed = to_minor(offer.get("ListPrice"), "CLP")
        images = item.get("images") or []
        return ScrapeResult(
            title=(product.get("productName") or "").strip(),
            price=price,
            list_price=listed if listed and price is not None and listed > price else None,
            currency="CLP",
            available=available,
            image_url=images[0].get("imageUrl") if images else None,
        )

    def item_label(self, item: dict) -> str:
        """Etiqueta de un item en el selector de variantes."""
        return (item.get("name") or item.get("itemId") or "").strip()

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        if not self.supports_variants:
            return []
        product = _product(raw, ref)
        items = product.get("items") or []
        if len(items) < 2:
            return []
        current = _item(product, ref).get("itemId")
        return [
            Variant(
                url=ref.canonical_url,
                label=self.item_label(it),
                external_id=ref.external_id,
                variant_id=str(it.get("itemId") or ""),
                selected=it.get("itemId") == current,
            )
            for it in items
        ]


def _product(raw: str, ref: ProductRef) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("la API de VTEX no devolvió JSON") from exc
    if not isinstance(data, list):
        raise FetchError("respuesta inesperada de la API de VTEX")
    if not data:
        raise NotFoundError(f"{ref.external_id} no existe en el catálogo")
    return data[0]


def _item(product: dict, ref: ProductRef) -> dict:
    items = product.get("items") or []
    if not items:
        raise FetchError("el producto no trae items")
    if not ref.variant_id:
        return items[0]
    for it in items:
        if str(it.get("itemId")) == ref.variant_id:
            return it
    raise NotFoundError(f"la variante {ref.variant_id} ya no existe")


def _offer(item: dict) -> dict:
    """La oferta del vendedor por defecto (o del primero).

    Sin vendedor u oferta la respuesta está incompleta: es un error de lectura, no un
    agotado (si no, `sold_out_without_price` lo dejaría pasar y avisaría OUT_OF_STOCK).
    """
    sellers = item.get("sellers") or []
    if not sellers:
        raise FetchError("el item no trae vendedores")
    seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0])
    offer = seller.get("commertialOffer")
    if not isinstance(offer, dict):
        raise FetchError("el vendedor no trae commertialOffer")
    return offer
