"""Procesador de Casaideas (casaideas.cl, Next.js sobre Magento 2 headless).

La ficha es `https://www.casaideas.cl/producto/<url_key>.html` (el url_key empieza con el
SKU: `3228759000011-bowl-…` o `c000000000342-cobertor-…` para los configurables). La
página es Next.js y se alimenta del GraphQL de Magento en `headless.casaideas.cl/graphql`,
que responde por GET, sin clave ni caché (`no-store`). Se lee ese GraphQL.

**La tienda oculta los agotados**: `products(filter: {url_key: …})` no los devuelve y la
ficha de Next.js da 404 (como si no existieran). `route(url: "<url_key>")`, en cambio,
resuelve la reescritura de URL y devuelve el producto con `stock_status: OUT_OF_STOCK` y
su precio. Un url_key inexistente da `route: null` → `NotFoundError`.

Precio: `price_range.minimum_price` (`final_price` y `regular_price`, el tachado). Montos
en pesos, sin decimales. `card_price` existe en el esquema pero viene vacío.

Configurables (sábanas, cobertores, toppers…): el único atributo es `talla` ("1.5 Plaza",
"2 Plazas", "King"). `variants` trae **solo las tallas con stock** (las agotadas
desaparecen, igual que en las Magento de `MagentoProcessor`). `variant_id` = SKU de la
talla, en la URL como `?sku=` (la tienda lo ignora). Sin talla se sigue "cualquier talla":
el precio más bajo entre las tallas con stock.
"""

import json
import re
from urllib.parse import parse_qs, urlsplit

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

API_URL = "https://headless.casaideas.cl/graphql"
_PRICE = "price_range { minimum_price { regular_price { value currency } final_price { value } } }"
QUERY = (
    "query Producto($url: String!) { route(url: $url) { __typename "
    "... on ProductInterface { sku name stock_status small_image { url } " + _PRICE + " } "
    "... on ConfigurableProduct { configurable_options { attribute_code label } "
    "variants { attributes { code label } product { sku stock_status " + _PRICE + " } } } } }"
)

_URL_RE = re.compile(
    r"^https?://(?:www\.)?casaideas\.cl/producto/([a-z0-9]+(?:-[a-z0-9]+)*)\.html/?(?:[?#].*)?$",
    re.I,
)
_SKU_RE = re.compile(r"^[A-Z0-9]{6,20}$")


class CasaideasProcessor(Processor):
    name = "casaideas"
    label = "Casaideas"
    fixture_ext = "json"
    home_url = "https://www.casaideas.cl/"
    example_url = (
        "https://www.casaideas.cl/producto/3228759000011-bowl-con-division-para-salsa.html"
    )
    platform = "Magento (GraphQL headless)"
    supports_variants = True
    supports_list_price = True
    # El GraphQL marca el agotado explícitamente (`stock_status`).
    sold_out_without_price = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (el precio más bajo, con stock en alguna) o tallas "
        "puntuales, cada una por separado. Las tallas agotadas no aparecen. Marca las que quieras."
    )
    notes = (
        "Decoración y hogar. Precio de la ficha; el precio normal tachado queda como precio "
        "antes. La tienda oculta los productos agotados (su página da 404), pero se siguen "
        "revisando. En sábanas y cobertores, sin elegir talla se sigue el precio más bajo "
        "entre las tallas con stock."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Casaideas")
        key = m.group(1).lower()
        sku = (parse_qs(urlsplit(url).query).get("sku") or [""])[0].strip().upper()
        sku = sku if _SKU_RE.match(sku) else ""
        return ProductRef(key, _url(key, sku), sku)

    def domain(self) -> str:
        return "headless.casaideas.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        params = {"query": QUERY, "variables": json.dumps({"url": ref.external_id})}
        return await get_text(API_URL, params=params)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = _product(raw, ref.external_id)
        title = (product.get("name") or "").strip()
        available = product.get("stock_status") == "IN_STOCK"
        sizes = _sizes(product)
        if ref.variant_id:
            size = next((s for s in sizes if s["sku"] == ref.variant_id), None)
            if size is None:
                # Talla agotada (o producto agotado): deja de listarse.
                return ScrapeResult(title, None, None, "CLP", False, _image(product))
            title = f"{title} ({size['label'][:1].lower()}{size['label'][1:]})"
            price, old, available = size["price"], size["old"], True
        elif sizes:
            cheapest = min(sizes, key=lambda s: s["price"] or 10**15)
            price, old = cheapest["price"], cheapest["old"]
        else:
            price, old = _prices(product)
        if price is None and available:
            raise FetchError("Casaideas no trae el precio del producto")
        return ScrapeResult(
            title=title,
            price=price,
            list_price=old if old and price is not None and old > price else None,
            currency="CLP",
            available=available,
            image_url=_image(product),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """ "Cualquier talla" y cada talla con stock (las agotadas no vienen)."""
        sizes = _sizes(_product(raw, ref.external_id))
        if len(sizes) < 2:
            return []
        out = [
            Variant(
                _url(ref.external_id),
                "Cualquier talla",
                ref.external_id,
                "",
                selected=not ref.variant_id,
            )
        ]
        for s in sizes:
            label = s["label"]
            if s["price"]:
                label += f": {_money(s['price'])}"
            out.append(
                Variant(
                    _url(ref.external_id, s["sku"]),
                    label,
                    ref.external_id,
                    s["sku"],
                    selected=s["sku"] == ref.variant_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)


def _url(key: str, sku: str = "") -> str:
    url = f"https://www.casaideas.cl/producto/{key}.html"
    return f"{url}?sku={sku}" if sku else url


def _product(raw: str, key: str) -> dict:
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise FetchError("Casaideas no devolvió JSON") from exc
    if not isinstance(body, dict) or body.get("errors"):
        errors = body.get("errors") if isinstance(body, dict) else None
        raise FetchError(f"error del GraphQL de Casaideas: {errors!r}"[:300])
    data = body.get("data")
    if not isinstance(data, dict) or "route" not in data:
        raise FetchError("la respuesta de Casaideas no trae `route`")
    route = data["route"]
    if route is None:
        raise NotFoundError(f"Casaideas no tiene el producto {key!r}")
    if not isinstance(route, dict) or not route.get("sku"):
        # Una categoría o página de contenido con ese url_key.
        raise NotFoundError(f"{key!r} no es un producto de Casaideas")
    return route


def _prices(product: dict) -> tuple[int | None, int | None]:
    """(precio final, precio normal) de `price_range.minimum_price`; 0 es "sin precio"."""
    minimum = (product.get("price_range") or {}).get("minimum_price") or {}
    final = to_minor((minimum.get("final_price") or {}).get("value"), "CLP")
    regular = to_minor((minimum.get("regular_price") or {}).get("value"), "CLP")
    return final or None, regular or None


def _sizes(product: dict) -> list[dict]:
    """Tallas con stock de un configurable: [{sku, label, price, old}]."""
    names = {
        o.get("attribute_code"): (o.get("label") or "").strip()
        for o in product.get("configurable_options") or []
    }
    out = []
    for variant in product.get("variants") or []:
        child = variant.get("product") or {}
        sku = str(child.get("sku") or "").upper()
        if not sku or child.get("stock_status") != "IN_STOCK":
            continue
        parts = [
            f"{names.get(a.get('code')) or 'Talla'} {(a.get('label') or '').strip()}"
            for a in variant.get("attributes") or []
        ]
        price, old = _prices(child)
        out.append({"sku": sku, "label": " / ".join(parts), "price": price, "old": old})
    return out


def _image(product: dict) -> str | None:
    url = (product.get("small_image") or {}).get("url")
    # Viene redimensionada por query (`?optimize=low&…`): sin ella es la original.
    return url.split("?", 1)[0] if url else None


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
