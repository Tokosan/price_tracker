"""Procesador de Librería Antártica (antartica.cl; Magento 2 detrás de Cloudflare).

Se lee la ficha HTML. El GraphQL de Magento (`/graphql`) existe, pero Cloudflare lo
bloquea ("Sorry, you have been blocked", 403) y además castiga a la IP unos minutos:
después de intentarlo, también las categorías respondían 403. La ficha pasa con httpx
y un User-Agent de navegador. Las referencias a `_px` del HTML son nombres de imágenes
(`…_1500x550_px.png`), no PerimeterX; igual se detectan las páginas de bloqueo de
Cloudflare y de PerimeterX por si llegan con HTTP 200.

La ficha es `/<url_key>.html`, un solo segmento, y el url_key termina en el ISBN o el
código de barras (`el-hombre-en-busca-del-sentido-9788425432026.html`, a veces con un
sufijo: `…-9788401035777-771354.html`). Las categorías también son `.html`
(`/promociones.html`, `/libros/ciencias.html`), pero no terminan en un número largo.

Precio: el `priceBox` del producto del formulario (`<input name="product" value=…>`):
`#product-price-<id>` es el precio final (lo paga cualquiera) y `#old-price-<id>`, el
"Precio habitual" tachado. No hay precio con tarjeta propia. Stock: el primer
`<div class="stock available|unavailable">` del bloque `product-info-stock-sku`. Un
agotado **no trae precio** (la ficha lo oculta y el JSON de Magento dice 0): como el
"Sin Stock" es una marca explícita, sin precio y sin stock es un agotado real
(`sold_out_without_price`). Si falta la marca de stock, es un error de lectura. Las
preventas ("Stock de venta anticipada") se compran: cuentan como disponibles.
"""

import html as htmllib
import re

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
)
from tracker.processors.http import get_text
from tracker.processors.util import to_minor

HOST = "www.antartica.cl"
# /<url_key>.html con el url_key terminado en un número de 8 o más dígitos (ISBN o EAN),
# opcionalmente seguido de otro número (url_key repetido que Magento desambigua).
_URL_RE = re.compile(
    r"^https?://(?:www\.)?antartica\.cl/([\w%-]*-\d{8,}(?:-\d+)?)\.html/?(?:[?#].*)?$",
    re.I,
)
_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_PID_RE = re.compile(r"<input\s+type=\"hidden\"\s+name=\"product\"\s+value=\"(\d+)\"")
_STOCK_RE = re.compile(r"class=\"product-info-stock-sku\">.*?<div class=\"stock (\w+)\"", re.S)
_TITLE_RE = re.compile(r"<span[^>]*data-ui-id=\"page-title-wrapper\"[^>]*>(.*?)</span>", re.S)
_IMAGE_RE = re.compile(r"itemprop=\"image\"\s+href=\"([^\"]+)\"")
_TAG_RE = re.compile(r"<[^>]+>")
# Bloqueo de Cloudflare ("Attention Required!", "Just a moment...") o de PerimeterX.
_BLOCKED_RE = re.compile(
    r"<title>\s*(?:Attention Required! \| Cloudflare|Just a moment\.\.\.|Robot or human\?)"
    r"|id=\"px-captcha\"",
    re.I,
)


class AntarticaProcessor(Processor):
    name = "antartica"
    label = "Antártica"
    home_url = "https://www.antartica.cl/"
    example_url = "https://www.antartica.cl/el-hombre-en-busca-del-sentido-9788425432026.html"
    platform = "Magento"
    supports_variants = False
    supports_list_price = True
    # Un agotado no trae precio, y la ficha lo marca explícitamente ("Sin Stock").
    sold_out_without_price = True
    notes = (
        "Librería: libros, agendas y regalos. Precio web (el que paga cualquiera); el precio "
        '"habitual" tachado queda como precio antes. Un agotado no muestra precio. Las '
        "preventas cuentan como disponibles."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de Antártica")
        key = m.group(1).lower()
        return ProductRef(key, f"https://{HOST}/{key}.html")

    def domain(self) -> str:
        return HOST

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        if _BLOCKED_RE.search(raw):
            raise FetchError("Antártica bloqueó la lectura (página de bloqueo del antibots)")
        og_type = _OG_TYPE_RE.search(raw)
        if not og_type or og_type.group(1).strip().lower() != "product":
            raise NotFoundError("no es una ficha de producto de Antártica")
        pid = _PID_RE.search(raw)
        stock = _STOCK_RE.search(raw)
        if not pid or not stock or stock.group(1) not in ("available", "unavailable"):
            raise FetchError("la ficha de Antártica no trae el producto o su stock")
        price = _amount(raw, "product-price", pid.group(1))
        old = _amount(raw, "old-price", pid.group(1))
        title = _TITLE_RE.search(raw)
        image = _IMAGE_RE.search(raw)
        return ScrapeResult(
            title=_text(title.group(1)) if title else "",
            price=price,
            list_price=old if old and price is not None and old > price else None,
            currency="CLP",
            available=stock.group(1) == "available",
            image_url=htmllib.unescape(image.group(1)) if image else None,
        )


def _amount(raw: str, kind: str, pid: str) -> int | None:
    m = re.search(rf"id=\"{kind}-{pid}\"\s+data-price-amount=\"([\d.]+)\"", raw)
    value = to_minor(m.group(1), "CLP") if m else None
    return value or None  # 0 es "sin precio" en Magento


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub(" ", fragment)).split())
