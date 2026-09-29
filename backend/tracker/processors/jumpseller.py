"""Base para tiendas Jumpseller (La Fortaleza, …).

Las URLs de producto son solo un slug (`/frosthaven`), igual que las de categorías,
así que no se distinguen por la URL: `parse` rechaza la página si no es de producto
(`og:type` distinto de `product` y sin JSON-LD `Product`).
"""

import html as htmllib
import re
from datetime import timedelta

from tracker.processors.base import NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.util import (
    availability_in_stock,
    digits_to_int,
    find_ld_product,
    first_offer,
    to_minor,
)

_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_TITLE_RE = re.compile(r"<meta\s+property=\"og:title\"\s+content=\"([^\"]*)\"", re.I)
_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]*)\"", re.I)
_META_RE = re.compile(
    r"<meta\s+property=\"product:(price:amount|price:currency|availability)\"\s+content=\"([^\"]*)\"",
    re.I,
)
# Con descuento, el precio original queda en #product-price con la clase `previous`
# y el final en #product-price-discount.
_PREVIOUS_RE = re.compile(
    r"<span\s+id=\"product-price\"\s+class=\"[^\"]*\bprevious\b[^\"]*\"[^>]*>([^<]+)<", re.I
)


class JumpsellerProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www) y `canonical_host`."""

    host: str = ""
    canonical_host: str = ""
    check_interval = timedelta(hours=12)
    platform = "Jumpseller"

    def __init__(self) -> None:
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(self.host)}/([a-z0-9][a-z0-9-]*)/?(?:[?#].*)?$",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = self._url_re.match(url.strip())
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        slug = m.group(1).lower()
        return ProductRef(slug, f"https://{self.canonical_host}/{slug}")

    def domain(self) -> str:
        return self.canonical_host

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = find_ld_product(raw)
        og_type = _OG_TYPE_RE.search(raw)
        if product is None and not (og_type and og_type.group(1).lower() == "product"):
            raise NotFoundError(f"{ref.canonical_url} no es una página de producto")

        title, price, available, currency = "", None, None, "CLP"
        if product:
            title = product.get("name") or ""
            offer = first_offer(product) or {}
            currency = offer.get("priceCurrency") or currency
            price = to_minor(offer.get("price"), currency)
            if offer.get("availability"):
                available = availability_in_stock(offer["availability"])

        metas = {k.lower(): v for k, v in _META_RE.findall(raw)}
        if price is None and metas.get("price:amount"):
            currency = metas.get("price:currency") or currency
            price = to_minor(metas["price:amount"], currency)
        if available is None and metas.get("availability"):
            available = metas["availability"].strip().lower() in {"instock", "in stock"}

        list_price = None
        m = _PREVIOUS_RE.search(raw)
        if m:
            previous = digits_to_int(htmllib.unescape(m.group(1)))
            if previous and price is not None and previous > price:
                list_price = previous

        if not title:
            m = _TITLE_RE.search(raw)
            title = htmllib.unescape(m.group(1)) if m else ""
        m = _IMAGE_RE.search(raw)
        return ScrapeResult(
            title=htmllib.unescape(title).strip(),
            price=price,
            list_price=list_price,
            currency=currency,
            available=bool(available),
            image_url=m.group(1) if m else None,
        )
