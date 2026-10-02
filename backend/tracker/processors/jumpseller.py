"""Base para tiendas Jumpseller (La Fortaleza, Vudu Gaming, …).

Las URLs de producto son solo un slug (`/frosthaven`), igual que las de categorías,
así que no se distinguen por la URL: `parse` rechaza la página si no es de producto
(`og:type` distinto de `product` y sin JSON-LD `Product`).

Las tiendas con varios idiomas anteponen el código (`/en/frosthaven`): el precio y la
moneda no cambian, así que el prefijo se descarta (`languages`).
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
    r"<meta\s+property=\"product:(price:amount|price:currency|original_price:amount|availability)\""
    r"\s+content=\"([^\"]*)\"",
    re.I,
)
# Con descuento, el precio original queda en #product-price con la clase `previous`
# y el final en #product-price-discount.
_PREVIOUS_RE = re.compile(
    r"<span\s+id=\"product-price\"\s+class=\"[^\"]*\bprevious\b[^\"]*\"[^>]*>([^<]+)<", re.I
)


class JumpsellerProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www) y `canonical_host`.

    `languages`: códigos de idioma que la tienda antepone a la ruta (`("en",)`).
    """

    host: str = ""
    canonical_host: str = ""
    languages: tuple[str, ...] = ()
    check_interval = timedelta(hours=12)
    platform = "Jumpseller"

    def __init__(self) -> None:
        lang = "|".join(re.escape(code) for code in self.languages)
        prefix = rf"(?:(?:{lang})/)?" if lang else ""
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(self.host)}/{prefix}"
            r"([a-z0-9][a-z0-9-]*)/?(?:[?#].*)?$",
            re.I,
        )

    def _slug(self, url: str) -> str | None:
        m = self._url_re.match(url.strip())
        if not m:
            return None
        slug = m.group(1).lower()
        # `/en` sola es la portada en inglés, no un producto.
        return None if slug in self.languages else slug

    def matches(self, url: str) -> bool:
        return self._slug(url) is not None

    def normalize(self, url: str) -> ProductRef:
        slug = self._slug(url)
        if slug is None:
            raise ValueError(f"no es una URL de producto de {self.label}")
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
        # El meta manda sobre el JSON-LD: un producto "no disponible" (preventa cerrada)
        # sale `InStock` en el JSON-LD pero `pending` en el meta (`oos` = agotado).
        if metas.get("availability"):
            available = metas["availability"].strip().lower() in {"instock", "in stock"}

        # Precio original: `#product-price.previous` (temas antiguos) o, si no, el meta
        # `product:original_price:amount` (lo traen todos los temas).
        previous = None
        m = _PREVIOUS_RE.search(raw)
        if m:
            previous = digits_to_int(htmllib.unescape(m.group(1)))
        elif metas.get("original_price:amount"):
            previous = to_minor(metas["original_price:amount"], currency)
        list_price = previous if previous and price is not None and previous > price else None

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
