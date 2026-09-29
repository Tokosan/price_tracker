"""Base para tiendas PrestaShop (Entrejuegos, DementeGames, …).

Cada tienda solo define su dominio y cómo se pide la página (directo o por
FlareSolverr); el parseo es común porque PrestaShop 1.7/8 expone los mismos datos.
"""

import html as htmllib
import json
import re
from datetime import timedelta

from tracker.processors.base import Processor, ProductRef, ScrapeResult
from tracker.processors.util import (
    availability_in_stock,
    digits_to_int,
    find_ld_product,
    first_offer,
    to_minor,
)

_DATA_PRODUCT_RE = re.compile(r"data-product=\"([^\"]*)\"")
_META_RE = re.compile(
    r"<meta\s+property=\"product:(price:amount|price:currency|availability)\"\s+content=\"([^\"]*)\"",
    re.I,
)
_REGULAR_RE = re.compile(r"class=\"regular-price\"[^>]*>([^<]+)<")
_TITLE_RE = re.compile(r"<meta\s+property=\"og:title\"\s+content=\"([^\"]*)\"", re.I)
_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]*)\"", re.I)

# Valores de `availability` en el data-product de PrestaShop 1.7/8.
_AVAILABLE = {"available", "last_remaining_items"}


class PrestaShopProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www), `canonical_host` y `fetch_raw`."""

    host: str = ""
    canonical_host: str = ""
    check_interval = timedelta(hours=12)
    platform = "PrestaShop"

    def __init__(self) -> None:
        # URL de producto: /<categoría>/…/<id>-<slug>.html
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(self.host)}/(?:[a-z0-9-]+/)*(\d+)-[^/?#]*\.html",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        clean = url.strip().split("#", 1)[0].split("?", 1)[0]
        m = self._url_re.match(clean)
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        clean = re.sub(r"^https?://(?:www\.)?[^/]+", f"https://{self.canonical_host}", clean)
        return ProductRef(m.group(1), clean)

    def domain(self) -> str:
        return self.canonical_host

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        """Tres fuentes en orden de confianza: data-product, JSON-LD y meta tags.

        El data-product (JSON que PrestaShop pone en #product-details) trae el
        precio con impuestos, la cantidad y el estado de stock. Si el tema cambia
        y desaparece, el JSON-LD y los meta `product:*` dan precio y stock.
        """
        title, price, available, currency = "", None, None, "CLP"
        list_price: int | None = None

        data = _data_product(raw)
        if data:
            title = data.get("name") or ""
            if data.get("price_amount") is not None:
                price = to_minor(data["price_amount"], currency)
            if data.get("availability"):
                available = data["availability"] in _AVAILABLE
            elif data.get("quantity") is not None:
                # Temas sin `availability` (p. ej. DementeGames): con cantidad 0 el
                # botón de compra queda deshabilitado, aunque sea preventa.
                available = int(data["quantity"]) > 0

        product = find_ld_product(raw)
        if product:
            title = title or product.get("name") or ""
            offer = first_offer(product) or {}
            currency = offer.get("priceCurrency") or currency
            if price is None:
                price = to_minor(offer.get("price"), currency)
            if available is None and offer.get("availability"):
                available = availability_in_stock(offer.get("availability"))

        metas = {k.lower(): v for k, v in _META_RE.findall(raw)}
        if price is None and metas.get("price:amount"):
            price = to_minor(metas["price:amount"], metas.get("price:currency") or currency)
        if available is None and metas.get("availability"):
            available = metas["availability"].strip().lower() in {"in stock", "instock"}

        # Precio base (tachado) del producto principal: el primer .regular-price
        # dentro de .product-prices; los demás son de productos relacionados.
        block_at = raw.find("product-prices")
        if block_at >= 0:
            m = _REGULAR_RE.search(raw, block_at, block_at + 3000)
            if m:
                regular = digits_to_int(htmllib.unescape(m.group(1)))
                if regular and price is not None and regular > price:
                    list_price = regular

        if not title:
            m = _TITLE_RE.search(raw)
            title = htmllib.unescape(m.group(1)) if m else ""
        m = _IMAGE_RE.search(raw)
        image = m.group(1) if m else None
        return ScrapeResult(
            title=htmllib.unescape(title).strip(),
            price=price,
            list_price=list_price,
            currency=currency,
            available=bool(available),
            image_url=image,
        )


def _data_product(raw: str) -> dict | None:
    for m in _DATA_PRODUCT_RE.finditer(raw):
        try:
            data = json.loads(htmllib.unescape(m.group(1)))
        except ValueError:
            continue
        if isinstance(data, dict) and "id_product" in data:
            return data
    return None
