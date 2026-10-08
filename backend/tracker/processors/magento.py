"""Base para tiendas Magento 2 (Sparta, Speedo, Head, New Balance…) vía la ficha HTML.

Se lee la ficha y no el GraphQL de Magento (`/graphql`), que en estas tiendas **oculta los
productos agotados** (y las tallas agotadas): un agotado y un link que no es de producto
dan lo mismo (`items: []`). La ficha de un agotado, en cambio, sigue en 200.

La ficha es `/<url_key>.html`, un solo segmento (el url_key suele terminar en el SKU). Las
categorías también son `/<algo>.html`, pero traen `og:type` distinto de `product` →
`NotFoundError`. Un link inexistente da 404. Cada color es su propio producto (su propio
link); el único atributo configurable es la talla.

Precio: el `priceBox` del producto del formulario (`<input name="product" value=…>`):
`#product-price-<id>` es el precio final y `#old-price-<id>`, el "Precio habitual"
tachado. El stock depende del tema (`stock_marker`):
- `"stock_div"`: `<div class="stock available|unavailable">` de `product-info-stock-sku`.
- `"availability"`: `<p class="availability in-stock|out-of-stock">`.
- `"cart_button"`: sin marca de texto. La ficha siempre trae el formulario de compra
  (`#product_addtocart_form`); con stock trae además el botón (`#product-addtocart-button`).
  Sin el formulario es un error de lectura, no un agotado.

Tallas: el `jsonConfig` del swatch-renderer (o el `spConfig` de los selectores sin
swatches) trae **solo las tallas vendibles** en `attributes[].options[].products`, con su
SKU (`sku`) y su precio (`optionPrices`, `finalPrice` y `oldPrice`). Una talla agotada
desaparece (o queda con `products: []`); un producto agotado completo no trae la
configuración y suele no traer precio (`product:price:amount` = 0). Como la ficha marca el
agotado, sin precio y sin stock es un agotado real (`sold_out_without_price`). `variant_id`
= SKU de la talla, en la URL como `?sku=` (la tienda lo ignora). Sin talla se sigue
"cualquier talla": el precio más bajo entre las tallas vendibles.

Subclases: `name`, `label`, `host` (sin www), `stock_marker` y los metadatos.
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

_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_OG_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]+)\"", re.I)
_PID_RE = re.compile(r"<input\s+type=\"hidden\"\s+name=\"product\"\s+value=\"(\d+)\"")
_STOCK_DIV_RE = re.compile(r"class=\"product-info-stock-sku\">\s*<div class=\"stock (\w+)\"", re.S)
_AVAILABILITY_RE = re.compile(r"<p class=\"availability (in-stock|out-of-stock)\">")
_FORM_RE = re.compile(r"id=\"product_addtocart_form\"")
_BUTTON_RE = re.compile(r"id=\"product-addtocart-button\"")
_TITLE_RE = re.compile(r"<span[^>]*data-ui-id=\"page-title-wrapper\"[^>]*>(.*?)</span>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_CONFIG_KEYS = ('"jsonConfig":', '"spConfig":')


class MagentoProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www), `stock_marker` y los metadatos."""

    host: str = ""
    stock_marker: str = "stock_div"  # "stock_div" | "availability" | "cart_button"
    platform = "Magento"
    supports_variants = True
    supports_list_price = True
    # Un agotado no trae precio (la ficha lo marca), y una talla agotada deja de listarse.
    sold_out_without_price = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (el precio más bajo, con stock en alguna) o tallas "
        "puntuales, cada una por separado. Las tallas agotadas no aparecen. Marca las que quieras."
    )

    def __init__(self) -> None:
        host = re.escape(self.host)
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{host}/([\w%-]+)\.html/?(?:[?#].*)?$", re.I
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = self._url_re.match(url)
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        key = m.group(1).lower()
        sku = (parse_qs(urlsplit(url).query).get("sku") or [""])[0].strip().upper()
        sku = sku if _SKU_RE.match(sku) else ""
        return ProductRef(key, self._url(key, sku), sku)

    def domain(self) -> str:
        return self.host

    def _url(self, key: str, sku: str = "") -> str:
        url = f"https://{self.host}/{key}.html"
        return f"{url}?sku={sku}" if sku else url

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("?", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        pid, available = self._product(raw)
        title_m = _TITLE_RE.search(raw)
        title = _text(title_m.group(1)) if title_m else ""
        image = _image(raw)
        sizes = self._sizes(raw)
        if ref.variant_id:
            if sizes is None and available:
                raise FetchError(f"la ficha de {self.label} no trae las tallas")
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
            raise FetchError(f"la ficha de {self.label} no trae el precio")
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
        self._product(raw)
        sizes = self._sizes(raw) or []
        if len(sizes) < 2:
            return []
        out = [
            Variant(
                self._url(ref.external_id),
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
                    self._url(ref.external_id, s["sku"]),
                    label,
                    ref.external_id,
                    s["sku"],
                    selected=s["sku"] == ref.variant_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)

    def _product(self, raw: str) -> tuple[str, bool]:
        """(id del producto, disponible). Lanza si no es una ficha o le falta la marca de stock."""
        og_type = _OG_TYPE_RE.search(raw)
        if not og_type or og_type.group(1).strip().lower() != "product":
            raise NotFoundError(f"no es una ficha de producto de {self.label}")
        pid = _PID_RE.search(raw)
        available = self._available(raw)
        if not pid or available is None:
            raise FetchError(f"la ficha de {self.label} no trae el producto o su stock")
        return pid.group(1), available

    def _available(self, raw: str) -> bool | None:
        if self.stock_marker == "stock_div":
            m = _STOCK_DIV_RE.search(raw)
            if not m or m.group(1) not in ("available", "unavailable"):
                return None
            return m.group(1) == "available"
        if self.stock_marker == "availability":
            m = _AVAILABILITY_RE.search(raw)
            return m.group(1) == "in-stock" if m else None
        if self.stock_marker == "cart_button":
            if not _FORM_RE.search(raw):
                return None
            return bool(_BUTTON_RE.search(raw))
        raise ValueError(f"stock_marker desconocido: {self.stock_marker}")

    def _sizes(self, raw: str) -> list[dict] | None:
        """Tallas vendibles: [{sku, label, price, old}]. None si la ficha no trae configuración."""
        start = -1
        for key in _CONFIG_KEYS:
            start = raw.find(key)
            if start >= 0:
                break
        if start < 0:
            return None
        try:
            config, _ = json.JSONDecoder().raw_decode(raw, raw.find("{", start))
        except ValueError as exc:
            raise FetchError(f"la configuración de tallas de {self.label} no es JSON") from exc
        if not isinstance(config, dict):
            raise FetchError(f"configuración de tallas inesperada en {self.label}")
        skus = config.get("sku") or {}
        prices = config.get("optionPrices") or {}
        labels: dict[str, list[str]] = {}
        for attribute in (config.get("attributes") or {}).values():
            for option in attribute.get("options") or []:
                for child in option.get("products") or []:
                    label = str(option.get("label") or "").strip()
                    labels.setdefault(str(child), []).append(label)
        out = []
        for child, parts in labels.items():
            sku = str(skus.get(child) or "").upper()
            if not sku:
                continue
            child_prices = prices.get(child) or {}
            price = _option_amount(child_prices.get("finalPrice"))
            old = _option_amount(child_prices.get("oldPrice"))
            label = " / ".join(p for p in parts if p)
            out.append({"sku": sku, "label": label, "price": price, "old": old})
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
    # La og:image viene redimensionada por query: sin ella es la original.
    return htmllib.unescape(m.group(1)).split("?", 1)[0]


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub(" ", fragment)).split())


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
