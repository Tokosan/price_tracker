"""Procesador de Puma Chile (cl.puma.com, Magento 2 con tema propio).

Se lee la ficha HTML. La URL es `/<slug>-<estilo>-<color>.html` (`…-392034-02.html`): un
estilo (6 dígitos) en un color (2 dígitos). `external_id` = `<estilo>_<color>` (el
"Art." de la ficha, el `sku` del JSON-LD y el `activeNumber` del selector de colores).
Cada color es su propio link; las tallas se eligen al agregar.

La ficha trae el `spConfig` del estilo completo: el atributo `color` con una opción por
color y el atributo `size` con las tallas. Cada opción separa sus hijos en `products`
(vendibles) y `out_of_stock` (agotados), con el SKU (EAN) de cada hijo en `skus` y el
precio en `optionPrices` (solo de los vendibles). El color de la ficha sale de la galería
(`"style_number":"<estilo>_<color>","color_id":"<id>"`). Así las tallas agotadas sí se
ven (con la marca "agotada"), y "sin precio y sin stock" es un agotado explícito
(`sold_out_without_price`).

Un color agotado completo **deja de publicarse**: su URL da 404 (la tienda oculta los
colores sin stock, `cv_out_of_stock_visibility`), aunque el estilo siga a la venta en
otros colores. Por eso, en las revisiones (`fetch`), un 404 del color se contrasta con la
URL del estilo sin color (`/<slug>-<estilo>.html`, que muestra el color por defecto): si
el estilo existe, el color está agotado; si tampoco existe, es un 404 de verdad. Al
agregar (`inspect`) un link que da 404 se rechaza.

`variant_id` = EAN de la talla, en la URL como `?sku=` (la tienda lo ignora). Sin talla
se sigue "cualquier talla": el precio más bajo entre las tallas vendibles del color.
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
from tracker.processors.util import find_ld_product, to_minor

HOST = "cl.puma.com"
_URL_RE = re.compile(
    r"^https?://cl\.puma\.com/([\w%-]+?)-(\d{6})-(\d{2})\.html/?(?:[?#].*)?$", re.I
)
_SKU_RE = re.compile(r"^\d{8,14}$")
_ACTIVE_RE = re.compile(r"\"activeNumber\":\s*\"(\d{6}_\d{2})\"")
_OG_IMAGE_RE = re.compile(r"<meta\s+property=\"og:image\"\s+content=\"([^\"]+)\"", re.I)
_SP_CONFIG = '"spConfig":'


class PumaProcessor(Processor):
    name = "puma"
    label = "Puma"
    home_url = "https://cl.puma.com/"
    example_url = "https://cl.puma.com/zapatilla-anzarun-lite-para-jovenes-372004-10.html"
    platform = "Magento"
    supports_variants = True
    supports_list_price = True
    # Las tallas agotadas vienen marcadas (`out_of_stock`) y sin precio.
    sold_out_without_price = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Cada color tiene su propio link. Puedes seguir cualquier talla (el precio más bajo, "
        "con stock en alguna) o tallas puntuales, cada una por separado. Marca las que quieras."
    )
    notes = (
        'Precio de la ficha; el precio tachado queda como precio "antes". Cada color tiene '
        "su propio link. Sin elegir talla se sigue el precio más bajo entre las tallas con "
        "stock. Puma deja de publicar un color agotado: se registra como agotado mientras el "
        "modelo siga a la venta en otro color."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Puma")
        slug, style, color = m.group(1).lower(), m.group(2), m.group(3)
        sku = (parse_qs(urlsplit(url).query).get("sku") or [""])[0].strip()
        sku = sku if _SKU_RE.match(sku) else ""
        return ProductRef(f"{style}_{color}", _url(slug, style, color, sku), sku)

    def domain(self) -> str:
        return HOST

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("?", 1)[0])

    async def fetch(self, ref: ProductRef) -> ScrapeResult:
        try:
            raw = await self.fetch_raw(ref)
        except NotFoundError:
            # Color agotado (Puma lo despublica) o producto dado de baja: se mira el estilo.
            style_url = re.sub(r"-\d{2}\.html$", ".html", ref.canonical_url.split("?", 1)[0])
            style_raw = await get_text(style_url)
            if _SP_CONFIG not in style_raw:
                raise FetchError(f"el estilo de {ref.external_id} no trae spConfig") from None
            return ScrapeResult("", None, None, "CLP", False, None)
        return self.parse(raw, ref)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        page = _page(raw, ref)
        details = [page["color"]] if page["color"] else []
        sizes = page["sizes"]
        if ref.variant_id:
            size = next((s for s in sizes if s["sku"] == ref.variant_id), None)
            if size is not None:
                details.append(f"talla {size['label']}")
            chosen = [size] if size is not None and size["available"] else []
        else:
            chosen = [s for s in sizes if s["available"]]
        title = f"{page['title']} ({', '.join(details)})" if details else page["title"]
        if not chosen:
            # Talla (o color completo) agotada: la marca `out_of_stock` lo confirma.
            return ScrapeResult(title, None, None, "CLP", False, page["image"])
        best = min(chosen, key=lambda s: s["price"] or 10**15)
        if best["price"] is None:
            raise FetchError("la talla con stock no trae precio")
        old = best["old"]
        return ScrapeResult(
            title=title,
            price=best["price"],
            list_price=old if old and old > best["price"] else None,
            currency="CLP",
            available=True,
            image_url=page["image"],
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """ "Cualquier talla" y cada talla del color (las agotadas, marcadas)."""
        page = _page(raw, ref)
        sizes = page["sizes"]
        if len(sizes) < 2:
            return []
        base = ref.canonical_url.split("?", 1)[0]
        out = [Variant(base, "Cualquier talla", ref.external_id, "", selected=not ref.variant_id)]
        for s in sizes:
            label = f"Talla {s['label']}"
            if s["price"]:
                label += f": {_money(s['price'])}"
            if not s["available"]:
                label += " (agotada)"
            out.append(
                Variant(
                    f"{base}?sku={s['sku']}",
                    label,
                    ref.external_id,
                    s["sku"],
                    selected=s["sku"] == ref.variant_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)


def _url(slug: str, style: str, color: str, sku: str = "") -> str:
    url = f"https://{HOST}/{slug}-{style}-{color}.html"
    return f"{url}?sku={sku}" if sku else url


def _page(raw: str, ref: ProductRef) -> dict:
    """Título, color, imagen y tallas del color de la ficha. Lanza si no es la ficha pedida."""
    product = find_ld_product(raw)
    if not product:
        raise NotFoundError("no es una ficha de producto de Puma")
    if str(product.get("sku") or "") != ref.external_id:
        raise FetchError(f"la ficha de Puma no es la de {ref.external_id}")
    active = _ACTIVE_RE.search(raw)
    if not active or active.group(1) != ref.external_id:
        raise FetchError(f"el selector de colores de Puma no está en {ref.external_id}")
    color_id = re.search(rf"\"style_number\":\"{ref.external_id}\",\"color_id\":\"(\d+)\"", raw)
    if not color_id:
        raise FetchError("la galería de Puma no trae el color de la ficha")
    config = _config(raw)
    attributes = {
        str(a.get("code")): a
        for a in (config.get("attributes") or {}).values()
        if isinstance(a, dict)
    }
    color = next(
        (
            o
            for o in (attributes.get("color") or {}).get("options") or []
            if str(o.get("id")) == color_id.group(1)
        ),
        None,
    )
    if color is None:
        raise FetchError("el spConfig de Puma no trae el color de la ficha")
    # Talla de cada hijo y su posición en el selector (el orden de la ficha).
    size_label: dict[str, tuple[int, str]] = {}
    for pos, option in enumerate((attributes.get("size") or {}).get("options") or []):
        for child in (option.get("products") or []) + (option.get("out_of_stock") or []):
            size_label[str(child)] = (pos, str(option.get("label") or "").strip())
    skus = config.get("skus") or {}
    prices = config.get("optionPrices") or {}
    sizes = []
    for available, children in (
        (True, color.get("products") or []),
        (False, color.get("out_of_stock") or []),
    ):
        for child in children:
            child = str(child)
            sku = str(skus.get(child) or "")
            if not sku:
                continue
            child_prices = prices.get(child) or {}
            pos, label = size_label.get(child, (10**6, ""))
            sizes.append(
                {
                    "pos": pos,
                    "sku": sku,
                    "label": label or sku,
                    "available": available,
                    "price": _amount(child_prices.get("finalPrice")) if available else None,
                    "old": _amount(child_prices.get("oldPrice")) if available else None,
                }
            )
    sizes.sort(key=lambda s: s["pos"])
    image = _OG_IMAGE_RE.search(raw)
    return {
        "title": " ".join(str(product.get("name") or "").split()),
        "color": str(color.get("label") or "").strip(),
        "image": htmllib.unescape(image.group(1)) if image else None,
        "sizes": sizes,
    }


def _config(raw: str) -> dict:
    start = raw.find(_SP_CONFIG)
    if start < 0:
        raise FetchError("la ficha de Puma no trae el spConfig")
    try:
        config, _ = json.JSONDecoder().raw_decode(raw, raw.find("{", start))
    except ValueError as exc:
        raise FetchError("el spConfig de Puma no es JSON válido") from exc
    if not isinstance(config, dict):
        raise FetchError("spConfig inesperado en la ficha de Puma")
    return config


def _amount(value) -> int | None:
    if not isinstance(value, dict):
        return None
    return to_minor(value.get("amount"), "CLP") or None


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
