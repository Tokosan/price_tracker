"""Procesador de PC Factory (pcfactory.cl).

La página es una SPA: nombre, stock y precios salen de la API del catálogo que usa
el propio front, en dos llamadas (`/productos/{id}` y `/productos/{id}/precio`).
`fetch_raw` las junta en un solo JSON `{"producto": …, "precio": …}`. No se usa
`api-dex-catalog`: el front no lo usa y sus datos no calzan con la página.

Precio = `efectivo` (transferencia o débito, el precio grande de la ficha); el de
crédito (`normal`) y `debito` se ignoran. `referencia` es el precio "antes".
"""

import json
import re
from datetime import timedelta
from decimal import Decimal

from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.util import to_minor

# /producto/<id> o /producto/<id>-<slug>; el slug no importa.
_URL_RE = re.compile(
    r"^https?://(?:www\.)?pcfactory\.cl/producto/(\d+)(?:-[^/?#]*)?/?(?:[?#].*)?$", re.I
)
API_URL = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos"
IMAGE_URL = "https://assets.pcfactory.cl/public/foto/{id}/1_500.jpg"
# Código de error de la API para "Ficha de producto [id] no disponible" (va con HTTP 404).
_NOT_FOUND_CODE = "1014"


class PcFactoryProcessor(Processor):
    name = "pcfactory"
    label = "PC Factory"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    home_url = "https://www.pcfactory.cl/"
    example_url = "https://www.pcfactory.cl/producto/1579-spektra-cable-usb-2-0-a-a-4-5m-extension"
    platform = "API de PC Factory"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio por transferencia o débito (el grande de la ficha); el precio con tarjeta "
        "de crédito no se guarda. Un producto agotado sigue mostrando su precio."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de PC Factory")
        product_id = str(int(m.group(1)))
        return ProductRef(product_id, f"https://www.pcfactory.cl/producto/{product_id}")

    def domain(self) -> str:
        return "www.pcfactory.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        base = f"{API_URL}/{ref.external_id}"
        producto = await get_text(base)
        precio = await get_text(f"{base}/precio")
        # Texto crudo de cada respuesta, sin re-serializar (los montos vienen con decimales).
        return f'{{"producto": {producto}, "precio": {precio}}}'

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw, parse_float=Decimal)
        except ValueError as exc:
            raise FetchError("la API de PC Factory no devolvió JSON") from exc
        if not isinstance(body, dict):
            raise FetchError("respuesta inesperada de la API de PC Factory")
        producto = _part(body, "producto", ref)
        precio = (_part(body, "precio", ref).get("precio")) or {}
        if str(producto.get("id")) != ref.external_id:
            raise FetchError(f"la API devolvió otro producto ({producto.get('id')!r})")

        price = to_minor(precio.get("efectivo"), "CLP")
        if price is not None and price <= 0:
            price = None  # un precio en cero es un dato roto, no una oferta
        ref_price = to_minor(precio.get("referencia"), "CLP")
        stock = str((producto.get("stock") or {}).get("aproximado") or "0").strip()
        return ScrapeResult(
            title=(producto.get("nombre") or "").strip(),
            price=price,
            list_price=ref_price if ref_price and price is not None and ref_price > price else None,
            currency="CLP",
            available=stock not in ("", "0"),
            image_url=IMAGE_URL.format(id=ref.external_id),
        )


def _part(body: dict, key: str, ref: ProductRef) -> dict:
    part = body.get(key)
    if not isinstance(part, dict):
        raise FetchError(f"falta '{key}' en la respuesta de PC Factory")
    errors = part.get("errors")
    if errors:
        codes = {str(e.get("code")) for e in errors if isinstance(e, dict)}
        if _NOT_FOUND_CODE in codes:
            raise NotFoundError(f"PC Factory no tiene el producto {ref.external_id}")
        raise FetchError(f"error de la API de PC Factory: {errors!r}")
    return part
