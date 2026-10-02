"""Procesador de SP Digital (spdigital.cl, Saleor).

Se lee el GraphQL de Saleor que usa la página (`bff.spdigital.cl`, canal `sp-digital`,
sin autenticación), con curl_cffi: está detrás de Cloudflare y con httpx el resultado
cambió entre el contenedor y el host; curl_cffi pasa en ambos.

Saleor solo sabe el precio "con otros medios de pago" (`pricing.priceRange.start`). La
página calcula el de transferencia con `metadata.pricing = {"sp-digital": {"cash": …,
"other": …}}`, que son los precios sin oferta: transferencia = `p · cash / other`,
redondeado hacia abajo a la decena, y el precio normal tachado es `cash`. Una caída
de `cash`/`other` (metadato roto) deja el precio en None antes que inventar uno.

Stock: `defaultVariant.quantityAvailable` (`isAvailableForPurchase` sigue en true sin
stock). Un slug que no existe responde `product: null`.
"""

import json
import re
from datetime import timedelta
from urllib.parse import quote, unquote, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
)
from tracker.processors.http import post_json_impersonate
from tracker.processors.util import to_minor

API_URL = "https://bff.spdigital.cl/api/v1/saleor"
CHANNEL = "sp-digital"
QUERY = """
query Producto($slug: String!, $channel: String!) {
  product(slug: $slug, channel: $channel) {
    name
    slug
    thumbnail(size: 512) { url }
    pricingMeta: metafield(key: "pricing")
    pricing { priceRange { start { gross { amount currency } } } }
    defaultVariant { quantityAvailable(address: { country: CL }) }
  }
}
""".strip()

_HOSTS = {"www.spdigital.cl", "spdigital.cl"}
# Un solo segmento: /<slug>/. Lo demás (categorías, búsquedas, landings) tiene más.
# Hay slugs con letras no ASCII ("…-en-español-…"), que el navegador codifica con %.
_PATH_RE = re.compile(r"^/([^\W_]+(?:-[^\W_]+)*)/?$")
_NOT_PRODUCT = {"categories", "search", "landing", "cart", "checkout", "account", "brands"}


class SpDigitalProcessor(Processor):
    name = "spdigital"
    label = "SP Digital"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    home_url = "https://www.spdigital.cl/"
    example_url = (
        "https://www.spdigital.cl/audifonos-gamer-hyperx-cloud-iii-s-wireless-over-ear-"
        "24ghz-bluetooth-pc-ps-moviles-blackred/"
    )
    platform = "Saleor (GraphQL)"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio por transferencia (lo puede pagar cualquiera); el precio normal tachado es "
        "el de transferencia sin oferta. El precio con otros medios de pago no se guarda."
    )

    def _slug(self, url: str) -> str | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS:
            return None
        m = _PATH_RE.match(unquote(parts.path))
        if not m or m.group(1).lower() in _NOT_PRODUCT:
            return None
        return m.group(1).lower()

    def matches(self, url: str) -> bool:
        return self._slug(url) is not None

    def normalize(self, url: str) -> ProductRef:
        slug = self._slug(url)
        if slug is None:
            raise ValueError("no es una URL de producto de SP Digital")
        return ProductRef(slug, f"https://www.spdigital.cl/{quote(slug)}/")

    def domain(self) -> str:
        return "bff.spdigital.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        payload = {"query": QUERY, "variables": {"slug": ref.external_id, "channel": CHANNEL}}
        return await post_json_impersonate(API_URL, payload)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("SP Digital no devolvió JSON") from exc
        if not isinstance(body, dict) or body.get("errors"):
            errors = body.get("errors") if isinstance(body, dict) else None
            raise FetchError(f"error del GraphQL de SP Digital: {errors!r}"[:300])
        data = body.get("data")
        if not isinstance(data, dict) or "product" not in data:
            raise FetchError("la respuesta de SP Digital no trae `product`")
        product = data["product"]
        if product is None:
            raise NotFoundError(f"SP Digital no tiene el producto {ref.external_id!r}")
        gross = (((product.get("pricing") or {}).get("priceRange") or {}).get("start") or {}).get(
            "gross"
        ) or {}
        currency = gross.get("currency") or "CLP"
        price, list_price = _transfer(to_minor(gross.get("amount"), currency), product)
        quantity = (product.get("defaultVariant") or {}).get("quantityAvailable")
        return ScrapeResult(
            title=(product.get("name") or "").strip(),
            price=price,
            list_price=list_price,
            currency=currency,
            available=isinstance(quantity, int) and quantity > 0,
            image_url=(product.get("thumbnail") or {}).get("url"),
        )


def _transfer(other_price: int | None, product: dict) -> tuple[int | None, int | None]:
    """(precio por transferencia, precio normal tachado) desde el metadato `pricing`."""
    try:
        meta = json.loads(product.get("pricingMeta") or "")[CHANNEL]
        cash, other = int(meta["cash"]), int(meta["other"])
    except (ValueError, TypeError, KeyError):
        return None, None
    if other_price is None or cash <= 0 or other <= 0:
        return None, None
    # Enteros de punta a punta: 10 · floor(p · cash / other / 10).
    price = 10 * ((other_price * cash) // (other * 10))
    return price, cash if cash > price else None
