"""Procesador de Sparta (sparta.cl, Magento 2 / Adobe Commerce detrás de Fastly).

Se lee la ficha HTML, como en Antártica. El GraphQL de Magento (`/graphql`) responde,
pero **oculta los productos agotados** (y las tallas agotadas): un agotado y un link que
no es de producto dan lo mismo (`items: []`). La ficha de un agotado, en cambio, sigue
en 200 con la marca "Agotado".

La ficha es `/<url_key>.html`, un solo segmento (el url_key termina en el SKU:
`…-1690000wt41222bk21.html`). Las categorías también son `/<algo>.html` (`/hombre.html`),
pero traen `og:type` distinto de `product` → `NotFoundError`. Un link inexistente da 404.
Cada color es su propio producto (su propio link); el único atributo configurable es la
talla (`ropa_talla`, `Talla Nacional`, `bici_talla`…).

Precio: el `priceBox` del producto del formulario (`<input name="product" value=…>`):
`#product-price-<id>` es el precio final y `#old-price-<id>`, el "Precio habitual"
tachado. Stock: el `<div class="stock available|unavailable">` de `product-info-stock-sku`.

Tallas: el `jsonConfig` del swatch-renderer trae **solo las tallas vendibles**
(`attributes[].options[].products`), con su SKU (`sku`) y su precio (`optionPrices`,
`finalPrice` y `oldPrice`). Una talla agotada desaparece del `jsonConfig`; un producto
agotado completo no trae `jsonConfig` ni precio (`product:price:amount` = 0). Como la ficha
marca el agotado explícitamente, sin precio y sin stock es un agotado real
(`sold_out_without_price`). `variant_id` = SKU de la talla, en la URL como `?sku=`
(Sparta lo ignora). Sin talla se sigue "cualquier talla": el precio más bajo entre las
tallas vendibles.
"""

import html as htmllib
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

HOST = "sparta.cl"
_URL_RE = re.compile(r"^https?://(?:www\.)?sparta\.cl/([\w%-]+)\.html/?(?:[?#].*)?$", re.I)
_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_OG_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]+)\"", re.I)
_PID_RE = re.compile(r"<input\s+type=\"hidden\"\s+name=\"product\"\s+value=\"(\d+)\"")
_STOCK_RE = re.compile(r"class=\"product-info-stock-sku\">\s*<div class=\"stock (\w+)\"", re.S)
_TITLE_RE = re.compile(r"<span[^>]*data-ui-id=\"page-title-wrapper\"[^>]*>(.*?)</span>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_JSON_CONFIG = '"jsonConfig":'


class SpartaProcessor(Processor):
    name = "sparta"
    label = "Sparta"
    home_url = "https://sparta.cl/"
    example_url = "https://sparta.cl/zapatillas-urbanas-mujer-montagne-radiance-blanco-68400radiancemwh01.html"
    platform = "Magento"
    supports_variants = True
    supports_list_price = True
    # Un agotado no trae precio (la ficha lo marca "Agotado"), y una talla agotada
    # desaparece del jsonConfig.
    sold_out_without_price = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (el precio más bajo, con stock en alguna) o tallas "
        "puntuales, cada una por separado. Las tallas agotadas no aparecen. Marca las que quieras."
    )
    notes = (
        'Artículos deportivos. Precio de la ficha; el "precio habitual" tachado queda como '
        "precio antes. Cada color tiene su propio link. Sin elegir talla se sigue el precio "
        "más bajo entre las tallas con stock; Sparta no muestra las tallas agotadas."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Sparta")
        key = m.group(1).lower()
        sku = (parse_qs(urlsplit(url).query).get("sku") or [""])[0].strip().upper()
        sku = sku if _SKU_RE.match(sku) else ""
        return ProductRef(key, _url(key, sku), sku)

    def domain(self) -> str:
        return HOST

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("?", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        pid, available = _product(raw)
        title_m = _TITLE_RE.search(raw)
        title = _text(title_m.group(1)) if title_m else ""
        image = _image(raw)
        sizes = _sizes(raw)
        if ref.variant_id:
            if sizes is None and available:
                raise FetchError("la ficha de Sparta no trae las tallas (jsonConfig)")
            size = next((s for s in sizes or [] if s["sku"] == ref.variant_id), None)
            if size is None:
                # Talla agotada (o producto agotado): deja de listarse.
                return ScrapeResult(title, None, None, "CLP", False, image)
            title = f"{title} (talla {size['label']})"
            price, old = size["price"], size["old"]
        elif sizes:
            cheapest = min(sizes, key=lambda s: s["price"] or 10**15)
            price, old = cheapest["price"], cheapest["old"]
        else:
            price, old = _amount(raw, "product-price", pid), _amount(raw, "old-price", pid)
        if price is None and available:
            raise FetchError("la ficha de Sparta no trae el precio")
        return ScrapeResult(
            title=title,
            price=price,
            list_price=old if old and price is not None and old > price else None,
            currency="CLP",
            available=available,
            image_url=image,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """ "Cualquier talla" y cada talla vendible (las agotadas no vienen en la ficha)."""
        _product(raw)
        sizes = _sizes(raw) or []
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
            label = f"Talla {s['label']}"
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
    url = f"https://{HOST}/{key}.html"
    return f"{url}?sku={sku}" if sku else url


def _product(raw: str) -> tuple[str, bool]:
    """(id del producto, disponible). Lanza si no es una ficha o le falta la marca de stock."""
    og_type = _OG_TYPE_RE.search(raw)
    if not og_type or og_type.group(1).strip().lower() != "product":
        raise NotFoundError("no es una ficha de producto de Sparta")
    pid = _PID_RE.search(raw)
    stock = _STOCK_RE.search(raw)
    if not pid or not stock or stock.group(1) not in ("available", "unavailable"):
        raise FetchError("la ficha de Sparta no trae el producto o su stock")
    return pid.group(1), stock.group(1) == "available"


def _sizes(raw: str) -> list[dict] | None:
    """Tallas vendibles del jsonConfig: [{sku, label, price, old}]. None si no hay jsonConfig."""
    start = raw.find(_JSON_CONFIG)
    if start < 0:
        return None
    try:
        config, _ = json.JSONDecoder().raw_decode(raw, raw.find("{", start))
    except ValueError as exc:
        raise FetchError("el jsonConfig de Sparta no es JSON válido") from exc
    if not isinstance(config, dict):
        raise FetchError("jsonConfig inesperado en la ficha de Sparta")
    skus = config.get("sku") or {}
    prices = config.get("optionPrices") or {}
    labels: dict[str, list[str]] = {}
    for attribute in (config.get("attributes") or {}).values():
        for option in attribute.get("options") or []:
            for child in option.get("products") or []:
                labels.setdefault(str(child), []).append(str(option.get("label") or "").strip())
    out = []
    for child, parts in labels.items():
        sku = str(skus.get(child) or "").upper()
        if not sku:
            continue
        child_prices = prices.get(child) or {}
        price = _option_amount(child_prices.get("finalPrice"))
        old = _option_amount(child_prices.get("oldPrice"))
        out.append(
            {"sku": sku, "label": " / ".join(p for p in parts if p), "price": price, "old": old}
        )
    return out


def _option_amount(value) -> int | None:
    if not isinstance(value, dict):
        return None
    return to_minor(value.get("amount"), "CLP") or None


def _amount(raw: str, kind: str, pid: str) -> int | None:
    m = re.search(rf"id=\"{kind}-{pid}\"\s+data-price-amount=\"([\d.]+)\"", raw)
    value = to_minor(m.group(1), "CLP") if m else None
    return value or None  # 0 es "sin precio" en Magento


def _image(raw: str) -> str | None:
    m = _OG_IMAGE_RE.search(raw)
    if not m:
        return None
    # La og:image viene redimensionada a 265 px por query: sin ella es la original.
    return htmllib.unescape(m.group(1)).split("?", 1)[0]


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub(" ", fragment)).split())


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
