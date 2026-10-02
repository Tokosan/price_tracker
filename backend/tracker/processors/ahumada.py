"""Procesador de Farmacias Ahumada (farmaciasahumada.cl, Salesforce Commerce Cloud).

Cada lectura hace dos peticiones:

1. La ficha HTML (`/<slug>-<pid>.html`), solo para el stock. `Product-Variation` dice
   `available: true` / "In Stock" incluso en lo que la ficha muestra "Producto sin stock":
   el stock real es por zona de despacho y la ficha lo trae en el botón de compra
   (`<button class="add-to-cart" data-pid=… data-is-unavailable="true|false">`, un include
   sin caché). Sin comuna elegida (como aquí) se usa el inventario por defecto de la
   tienda. Un pid inexistente da 404 en la ficha; un slug viejo redirige (301) al nuevo.
2. `Product-Variation?pid=<pid>` (JSON, ~20 KB) para precio, título e imagen:
   `price.sales.value` es el precio para todo medio de pago y `price.list.value` el
   normal tachado (`null` sin descuento). `hasFamiliaAhumadaPrice` (club) se ignora.

De la ficha solo se guarda lo que se usa (`data-action` de la página y el botón), junto
al JSON, para que las fixtures no pesen 600 KB. No hay variantes: cada talla o
presentación es su propio producto, con su propio pid.
"""

import json
import re

from tracker.processors.base import FetchError, NotFoundError, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.sfcc import SFCCProcessor
from tracker.processors.util import to_minor

_ACTION_RE = re.compile(r"<div\s+class=\"page\"\s+data-action=\"([^\"]*)\"")
_UNAVAILABLE_RE = re.compile(r"\bdata-is-unavailable=\"(true|false)\"")


def pdp_summary(html: str, pid: str) -> dict:
    """De la ficha: el controlador de la página y el botón de compra del producto."""
    action = _ACTION_RE.search(html)
    button = re.search(
        rf"<button\s+class=\"add-to-cart(?:\s[^\"]*)?\"[^>]*\bdata-pid=\"{re.escape(pid)}\"[^>]*>",
        html,
    )
    return {
        "action": action.group(1) if action else None,
        "add_to_cart": button.group(0) if button else None,
    }


class AhumadaProcessor(SFCCProcessor):
    name = "ahumada"
    label = "Farmacias Ahumada"
    hosts = frozenset({"www.farmaciasahumada.cl", "farmaciasahumada.cl"})
    canonical_host = "www.farmaciasahumada.cl"
    site_id = "ahumada-cl"
    # Los pid van de 1 a 8 dígitos (`…-x-20-comprimidos-6.html`, `…-32006004.html`).
    path_re = re.compile(r"^/(?P<slug>[^/]+?)-(?P<pid>\d{1,10})\.html$", re.I)
    fixture_ext = "json"
    home_url = "https://www.farmaciasahumada.cl/"
    example_url = (
        "https://www.farmaciasahumada.cl/"
        "protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html"
    )
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio para todo medio de pago; el precio Familia Ahumada (club) no se guarda. "
        "Stock de la venta online sin comuna elegida: en tu comuna puede ser distinto."
    )

    async def fetch_raw(self, ref: ProductRef) -> str:
        html = await get_text(ref.canonical_url)  # pid inexistente → 404 → NotFoundError
        pdp = pdp_summary(html, ref.external_id)
        if pdp["action"] != "Product-Show":
            # Una página de contenido con forma de ficha: Product-Variation daría HTTP 500.
            raise NotFoundError(f"{ref.canonical_url} no es una ficha de producto")
        variation = await get_text(
            self.controller_url("Product-Variation"),
            params={"pid": ref.external_id, "quantity": "1"},
        )
        # Texto crudo del JSON, sin re-serializar (como Paris).
        return f'{{"pdp": {json.dumps(pdp, ensure_ascii=False)}, "variation": {variation}}}'

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        pdp, product = _load(raw)
        if pdp.get("action") != "Product-Show":
            raise NotFoundError(f"{ref.canonical_url} no es una ficha de producto")
        if str(product.get("id")) != ref.external_id:
            raise FetchError(f"Ahumada respondió el producto {product.get('id')!r}")
        unavailable = _UNAVAILABLE_RE.search(pdp.get("add_to_cart") or "")
        if not unavailable:
            raise FetchError("la ficha de Ahumada no trae el botón de compra del producto")
        prices = product.get("price") or {}
        sales = prices.get("sales") or {}
        currency = sales.get("currency") or "CLP"
        price = to_minor(sales.get("value"), currency) or None  # 0 = sin precio
        normal = to_minor((prices.get("list") or {}).get("value"), currency)
        large = (product.get("images") or {}).get("large") or []
        return ScrapeResult(
            title=(product.get("productName") or "").strip(),
            price=price,
            list_price=normal if normal and price is not None and normal > price else None,
            currency=currency,
            available=product.get("available") is True and unavailable.group(1) == "false",
            image_url=(large[0].get("url") if large and isinstance(large[0], dict) else None),
        )


def _load(raw: str) -> tuple[dict, dict]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("Ahumada no devolvió JSON") from exc
    pdp = data.get("pdp") if isinstance(data, dict) else None
    variation = data.get("variation") if isinstance(data, dict) else None
    product = variation.get("product") if isinstance(variation, dict) else None
    if not isinstance(pdp, dict) or not isinstance(product, dict) or not product.get("id"):
        raise FetchError("la respuesta de Ahumada no trae el producto")
    return pdp, product
