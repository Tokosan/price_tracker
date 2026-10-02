"""Procesador de abc (abc.cl, fusión de La Polar y AbcDin; Salesforce Commerce Cloud).

Se lee la ficha HTML: `Product-Variation` falla con los bundles ("combos"). Los links
viejos de lapolar.cl y abcdin.cl redirigen a abc.cl con el mismo ID, así que se aceptan
los tres y se normalizan a `https://www.abc.cl/<id>.html` (la tienda redirige a la URL
con slug). Cada talla o color tiene su propio ID y su propia URL.

Los precios del producto están en el bloque `.product-detail`, antes de su primer botón
`add-to-cart`; después vienen los componentes de un bundle y los productos relacionados,
con sus propios precios. Ahí, `.js-internet-price` es el precio para cualquier medio de
pago, `.js-normal-price` el normal tachado y `.js-tlp-price` el de la tarjeta de la
tienda, que no se usa. Cada uno lleva `.price-value[data-value="5500.0"]`.
"""

import html as htmllib
import re

from tracker.processors.base import FetchError, NotFoundError, ProductRef, ScrapeResult
from tracker.processors.http import get_text
from tracker.processors.sfcc import SFCCProcessor
from tracker.processors.util import to_minor

_DETAIL_RE = re.compile(r"class=\"[^\"]*\bproduct-detail\b[^\"]*\"\s+data-pid=\"(\d+)\"")
_BUTTON_RE = re.compile(r"<button\s+class=\"add-to-cart\b[^\"]*\"([^>]*)>(.*?)</button>", re.S)
_PRICE_RE = {
    kind: re.compile(
        rf"class=\"[^\"]*\bjs-{kind}-price\b[^\"]*\".*?"
        r"class=\"price-value\"\s+data-value=\"([\d.]+)\"",
        re.S,
    )
    for kind in ("internet", "normal")
}
_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_OG_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]*)\"", re.I)
_TITLE_RE = re.compile(r"<h1[^>]*class=\"[^\"]*\bproduct-name\b[^\"]*\"[^>]*>(.*?)</h1>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


class AbcProcessor(SFCCProcessor):
    name = "abc"
    label = "abc"
    hosts = frozenset(
        f"{www}{host}" for host in ("abc.cl", "lapolar.cl", "abcdin.cl") for www in ("", "www.")
    )
    canonical_host = "www.abc.cl"
    site_id = "Abc"
    locale = "es_CL"
    # /<slug>/<id>.html o /<id>.html (los bundles tienen IDs cortos, como 29914).
    path_re = re.compile(r"^/(?:[^/]+/)*(?P<pid>\d{4,})\.html$", re.I)
    home_url = "https://www.abc.cl/"
    example_url = "https://www.abc.cl/zapatilla-lona-hombre-icono/28767943.html"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Incluye los links de La Polar y AbcDin, que ahora son abc. Precio Internet; el precio "
        "con tarjeta de la tienda no se guarda. Cada talla o color tiene su propio link: pega "
        "el de la variante que quieres seguir."
    )

    def canonical_path(self, m: re.Match) -> str:
        return f"/{m.group('pid')}.html"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        og_type = _OG_TYPE_RE.search(raw)
        if og_type and og_type.group(1).strip().lower() != "product":
            raise NotFoundError(f"no es una ficha de producto (og:type {og_type.group(1)!r})")
        detail = _DETAIL_RE.search(raw)
        if not detail:
            raise FetchError("la ficha de abc no trae el bloque del producto")
        button = _BUTTON_RE.search(raw, detail.end())
        # Sin botón no se sabe dónde termina el bloque: mejor sin precio que uno ajeno.
        block = raw[detail.end() : button.start()] if button else ""
        internet = _price(block, "internet")
        normal = _price(block, "normal")
        price = internet if internet is not None else normal
        title = _TITLE_RE.search(raw)
        image = _OG_IMAGE_RE.search(raw)
        return ScrapeResult(
            title=_text(title.group(1)) if title else "",
            price=price,
            list_price=normal if internet is not None and normal and normal > internet else None,
            currency="CLP",
            available=bool(button)
            and not re.search(r"\bdisabled\b", button.group(1))
            and "agotado" not in _text(button.group(2)).lower(),
            image_url=htmllib.unescape(image.group(1)) if image else None,
        )


def _price(block: str, kind: str) -> int | None:
    m = _PRICE_RE[kind].search(block)
    return to_minor(m.group(1), "CLP") if m else None


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub(" ", fragment)).split())
