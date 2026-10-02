"""Procesador de Preunic (preunic.cl, perfumería y cuidado personal; Spree).

La web es una SPA de React Router (el HTML llega vacío), así que se lee la misma API que
usa el front: un BFF en `api.preunic.cl` delante de la Storefront API v2 de Spree, con
los campos en camelCase y algunos propios de Preunic. `GET
/bff-pu-ecommerce/bff/spr/products/<slug>?include=variants,…&api-key=<clave>` devuelve el
producto en formato JSON:API: `data` (el producto) e `included` (variantes, imágenes,
categorías). La clave es pública (va en el JS de la tienda) y el BFF responde 403 si la
petición no trae `Origin: https://preunic.cl`. Un slug inexistente responde 404.

La ficha muestra la variante `relationships.defaultVariant` (no hay un parámetro de URL
que elija otra). Casi todos los productos tienen una sola variante; no se ofrecen
variantes. En esa variante:
- `price`: precio normal (string, "1599.0"); el `price` del producto es el de la variante
  maestra y no coincide con lo que se muestra.
- `offerPrice`: precio con las promociones que no piden tarjeta. Si es menor que `price`,
  es el precio y `price` queda como precio "antes".
- `cardPrice`: precio con tarjeta SBPay (promociones `promotionCard: true`). No se usa.
- `compareAtPrice` viene en 0 y la ficha no lo usa.

Stock: la ficha habilita "Agregar" según la comuna elegida, que por defecto es Santiago
(`county_id` 340, zona de catálogo 39): disponible si `storeExclusive` y la comuna está
en `communes`, o si la zona está en `zones`, o si no es `storeExclusive` y `inStock`. Se
replica esa regla con la comuna por defecto. `inStock` viene en false en todo el catálogo
muestreado; los agotados tienen `communes` y `zones` vacíos y conservan su precio.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text

_HOSTS = frozenset({"preunic.cl", "www.preunic.cl"})
_PATH_RE = re.compile(r"^/products/([a-z0-9-]+)/?$", re.I)
API_URL = "https://api.preunic.cl/bff-pu-ecommerce/bff/spr/products/{slug}"
# Clave pública del BFF: la misma que manda el front desde el navegador.
API_KEY = "7d862486-d383-4c0c-8624-86d3832c0c0a"
INCLUDE = "variants,images,product_properties,taxons"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://preunic.cl",
    "Referer": "https://preunic.cl/",
}
# Comuna y zona de catálogo por defecto de la tienda (Santiago).
DEFAULT_COUNTY = 340
DEFAULT_ZONE = 39


class PreunicProcessor(Processor):
    name = "preunic"
    label = "Preunic"
    fixture_ext = "json"
    home_url = "https://preunic.cl/"
    example_url = "https://preunic.cl/products/cotonitos-de-algodon-270-unidades-nenito-s"
    platform = "Spree (API del front)"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio de la web con las ofertas que no piden tarjeta; el precio normal queda como "
        "precio «antes». El precio con tarjeta SBPay no se guarda. Stock de la comuna por "
        "defecto de la tienda (Santiago)."
    )

    def _slug(self, url: str) -> str | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS:
            return None
        m = _PATH_RE.match(parts.path)
        return m.group(1).lower() if m else None

    def matches(self, url: str) -> bool:
        return self._slug(url) is not None

    def normalize(self, url: str) -> ProductRef:
        slug = self._slug(url)
        if not slug:
            raise ValueError("no es una URL de producto de Preunic")
        return ProductRef(slug, f"https://preunic.cl/products/{slug}")

    def domain(self) -> str:
        return "preunic.cl"

    def api_url(self, slug: str) -> str:
        return API_URL.format(slug=slug)

    async def fetch_raw(self, ref: ProductRef) -> str:
        # get_text convierte el 404 de un slug inexistente en NotFoundError.
        return await get_text(
            self.api_url(ref.external_id),
            params={"include": INCLUDE, "api-key": API_KEY},
            headers=HEADERS,
        )

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("la API de Preunic no devolvió JSON") from exc
        # Cuerpo del 404 de un slug inexistente (fetch_raw ya lo corta por el status).
        if isinstance(body, dict) and "could not be found" in str(body.get("error") or ""):
            raise NotFoundError(f"Preunic no tiene el producto {ref.external_id!r}")
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict) or data.get("type") != "product":
            raise FetchError("falta el producto en la respuesta de Preunic")
        variant = _default_variant(data, body.get("included"))
        attrs = data.get("attributes") or {}

        regular = _amount(variant.get("price"))
        offer = _amount(variant.get("offerPrice"))
        price = offer if offer is not None and regular is not None and offer < regular else regular
        return ScrapeResult(
            title=(attrs.get("name") or variant.get("name") or "").strip(),
            price=price,
            list_price=regular
            if price is not None and regular is not None and regular > price
            else None,
            currency=variant.get("currency") or attrs.get("currency") or "CLP",
            available=_available(variant),
            image_url=_image(data, body.get("included")),
        )


def _default_variant(data: dict, included) -> dict:
    """Atributos de la variante que muestra la ficha (`defaultVariant`)."""
    rel = (data.get("relationships") or {}).get("defaultVariant") or {}
    variant_id = (rel.get("data") or {}).get("id")
    for item in included if isinstance(included, list) else []:
        if (
            isinstance(item, dict)
            and item.get("type") == "variant"
            and item.get("id") == variant_id
            and isinstance(item.get("attributes"), dict)
        ):
            return item["attributes"]
    raise FetchError(f"la variante por defecto ({variant_id!r}) no viene en la respuesta")


def _amount(value) -> int | None:
    """Monto en CLP ("1599.0" o 1599) a entero. Cero, negativo o no numérico = None."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return int(amount.to_integral_value())


def _available(variant: dict) -> bool:
    """Regla de la ficha para habilitar "Agregar", con la comuna por defecto (Santiago).

    Si falta algún campo es un error de lectura, no un agotado: si no, un cambio en la API
    dispararía OUT_OF_STOCK en todos los productos.
    """
    exclusive = variant.get("storeExclusive")
    in_stock = variant.get("inStock")
    communes = variant.get("communes")
    zones = variant.get("zones")
    if not isinstance(exclusive, bool) or not isinstance(in_stock, bool):
        raise FetchError("falta storeExclusive o inStock en la variante de Preunic")
    if not isinstance(communes, list) or not isinstance(zones, list):
        raise FetchError("faltan communes o zones en la variante de Preunic")
    return (
        (exclusive and DEFAULT_COUNTY in communes)
        or DEFAULT_ZONE in zones
        or (not exclusive and in_stock)
    )


def _image(data: dict, included) -> str | None:
    rel = (data.get("relationships") or {}).get("images") or {}
    ids = [i.get("id") for i in rel.get("data") or [] if isinstance(i, dict)]
    images = {
        item.get("id"): item.get("attributes") or {}
        for item in (included if isinstance(included, list) else [])
        if isinstance(item, dict) and item.get("type") == "image"
    }
    for image_id in ids:
        attrs = images.get(image_id) or {}
        styles = attrs.get("styles") or []
        url = attrs.get("blobUrl") or (
            styles[0].get("url") if styles and isinstance(styles[0], dict) else None
        )
        if url:
            return url
    return None
