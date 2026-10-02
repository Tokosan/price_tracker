"""Base para tiendas Jumpseller (La Fortaleza, Vudu Gaming, …).

Las URLs de producto son solo un slug (`/frosthaven`), igual que las de categorías,
así que no se distinguen por la URL: `parse` rechaza la página si no es de producto
(`og:type` distinto de `product` y sin JSON-LD `Product`).

Las tiendas con varios idiomas anteponen el código (`/en/frosthaven`): el precio y la
moneda no cambian, así que el prefijo se descarta (`languages`).

Las variantes por opciones no se pueden elegir: se sigue el precio por defecto. La
excepción son las preventas con una opción de reserva ("MONTO PARA RESERVA": 100 % /
50 %), donde el precio por defecto es el abono: ahí se toma el de la variante "100%".
"""

import html as htmllib
import json
import logging
import re
from datetime import timedelta

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
)
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
# Temas nuevos: variantes (precio y valores de opción) y opciones con nombre.
_PRODUCT_JSON_RE = re.compile(
    r"<script\s+type=\"application/json\"\s+class=\"product-json\"[^>]*>(.*?)</script>", re.S
)
_FORM_JSON_RE = re.compile(
    r"<script\s+type=\"application/json\"\s+class=\"product-form-json\"[^>]*>(.*?)</script>",
    re.S,
)
_RESERVA_RE = re.compile(r"reserva|abono", re.I)
_FULL_RE = re.compile(r"^\s*100\s*%\s*$")
# Valores conocidos del meta `product:availability`; otro valor no pisa al JSON-LD.
_META_IN_STOCK = {"instock", "in stock"}
_META_NO_STOCK = {"oos", "pending", "out of stock"}

log = logging.getLogger(__name__)


def _json(pattern: re.Pattern, raw: str):
    m = pattern.search(raw)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _reservation_price(raw: str, currency: str) -> tuple[int | None, int | None]:
    """(precio final, precio sin descuento) de la variante completa de una preventa con
    reserva, o (None, None) si el producto no tiene una opción de reserva."""
    form = _json(_FORM_JSON_RE, raw) or {}
    options = ((form.get("info") or {}).get("product") or {}).get("options") or []
    reserva_ids = {o.get("id") for o in options if _RESERVA_RE.search(o.get("name") or "")}
    variants = _json(_PRODUCT_JSON_RE, raw)
    if not reserva_ids or not isinstance(variants, list) or not variants:
        return None, None

    def is_full(v: dict) -> bool:
        return any(
            (val.get("value") or {}).get("option") in reserva_ids
            and _FULL_RE.match((val.get("value") or {}).get("name") or "")
            for val in v.get("values") or []
        )

    def prices(v: dict) -> tuple[int | None, int | None]:
        base = to_minor(v.get("price"), currency)
        discount = to_minor(v.get("discount"), currency) or 0
        return (base - discount if base is not None else None), base

    full = [v for v in variants if isinstance(v, dict) and is_full(v)]
    if full:
        return prices(full[0])
    candidates = [prices(v) for v in variants if isinstance(v, dict)]
    candidates = [c for c in candidates if c[0] is not None]
    return max(candidates) if candidates else (None, None)


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
        # sale `InStock` en el JSON-LD pero `pending` en el meta (`oos` = agotado). Un valor
        # desconocido no se adivina: queda el del JSON-LD.
        meta_av = (metas.get("availability") or "").strip().lower()
        if meta_av in _META_IN_STOCK:
            available = True
        elif meta_av in _META_NO_STOCK:
            available = False
        elif meta_av:
            log.warning("%s: product:availability desconocido %r", ref.canonical_url, meta_av)
        if available is None:
            raise FetchError(f"{ref.canonical_url}: la página no trae la disponibilidad")

        # Precio original: `#product-price.previous` (temas antiguos) o, si no, el meta
        # `product:original_price:amount` (lo traen todos los temas).
        previous = None
        m = _PREVIOUS_RE.search(raw)
        if m:
            previous = digits_to_int(htmllib.unescape(m.group(1)))
        elif metas.get("original_price:amount"):
            previous = to_minor(metas["original_price:amount"], currency)
        list_price = previous if previous and price is not None and previous > price else None

        full_price, full_base = _reservation_price(raw, currency)
        if full_price is not None:
            price = full_price
            list_price = full_base if full_base and full_base > full_price else None

        if not title:
            m = _TITLE_RE.search(raw)
            title = htmllib.unescape(m.group(1)) if m else ""
        m = _IMAGE_RE.search(raw)
        return ScrapeResult(
            title=htmllib.unescape(title).strip(),
            price=price,
            list_price=list_price,
            currency=currency,
            available=available,
            image_url=m.group(1) if m else None,
        )
