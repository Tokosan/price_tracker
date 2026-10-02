"""Procesador de Ripley (simple.ripley.cl, Next.js).

La ficha trae el producto en `__NEXT_DATA__` (`props.pageProps.detailProps.data.product`).
Cloudflare bloquea el fingerprint TLS de httpx (403), así que se pide con curl_cffi
imitando a Chrome.

Precios en `price`: `sale` es el precio internet, `master` el normal tachado y `ripley`
el de la Tarjeta Ripley, que no se usa. `parentpricestock` es lo que muestra la ficha
antes de elegir talla (el precio más bajo y si hay stock en alguna); cada talla o color
está en `variants[]` con su propio `sku`, precio y `stock`, que puede ser distinto.

La URL es `/<slug>-<id>` y el ID es lo que importa: `https://simple.ripley.cl/<id>`
redirige a la ficha (con cualquier slug). El ID puede ser del producto (`…p`, `mpm…`) o
de una talla (sin `p`), que lleva a la ficha del producto. Las tallas no tienen URL
propia: se siguen con `?sku=<sku>` en la URL (lo agrega el selector; Ripley lo ignora).
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
from tracker.processors.http import get_text_impersonate
from tracker.processors.util import to_minor

_HOSTS = {"simple.ripley.cl"}
# Un solo segmento: /<slug>-<id> o /<id>. Las categorías y búsquedas tienen más.
_PATH_RE = re.compile(r"^/(?:[a-z0-9-]*-)?(\d{7,}p?|mpm\d{8,})/?$", re.I)
_SKU_RE = re.compile(r"^\d{5,20}$")
_NEXT_RE = re.compile(
    r"<script[^>]*\bid=[\"']?__NEXT_DATA__[\"']?[^>]*>(.*?)</script>", re.S | re.I
)


class RipleyProcessor(Processor):
    name = "ripley"
    label = "Ripley"
    home_url = "https://simple.ripley.cl/"
    example_url = (
        "https://simple.ripley.cl/almohada-cic-da-soft-sleep-70-x-50-cm-blanco-2000385824701p"
    )
    platform = "Next.js"
    supports_variants = True
    supports_list_price = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (el precio más bajo, con stock en alguna) o tallas "
        "puntuales, cada una por separado. Marca las que quieras."
    )
    notes = (
        "Precio internet; el precio con Tarjeta Ripley no se guarda. Sin elegir talla se "
        "sigue lo que muestra la ficha: el precio más bajo y si queda stock en alguna talla."
    )

    def _match(self, url: str) -> tuple[re.Match, str] | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS:
            return None
        m = _PATH_RE.match(parts.path)
        return (m, parts.query) if m else None

    def matches(self, url: str) -> bool:
        return self._match(url) is not None

    def normalize(self, url: str) -> ProductRef:
        found = self._match(url)
        if not found:
            raise ValueError("no es una URL de producto de Ripley")
        m, query = found
        pid = m.group(1).lower()
        sku = (parse_qs(query).get("sku") or [""])[0].strip()
        return ProductRef(pid, _url(pid, sku), sku if _SKU_RE.match(sku) else "")

    def domain(self) -> str:
        return "simple.ripley.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text_impersonate(_url(ref.external_id))

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = _product(raw)
        title = (product.get("name") or "").strip()
        if ref.variant_id:
            variant = _variant(product, ref.variant_id)
            if variant is None:
                raise FetchError(
                    f"la talla (sku {ref.variant_id}) ya no está en la ficha de Ripley"
                )
            label = _label(variant)
            if label:
                title = f"{title} ({label})"
            source = variant
            available = variant.get("stock") is True and variant.get("isEnabled") is not False
        else:
            source = product.get("parentpricestock") or {}
            available = source.get("stock") is True
        price, list_price = _prices(source)
        return ScrapeResult(
            title=title,
            price=price,
            list_price=list_price,
            currency="CLP",
            available=available,
            image_url=_image(product),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las tallas o colores de la ficha, más "cualquier talla" (el link sin sku)."""
        product = _product(raw)
        variants = [v for v in product.get("variants") or [] if _SKU_RE.match(str(v.get("sku")))]
        if len(variants) < 2:
            return []
        price, _ = _prices(product.get("parentpricestock") or {})
        any_label = "Cualquier talla" + (f": desde {_money(price)}" if price is not None else "")
        out = [
            Variant(
                _url(ref.external_id), any_label, ref.external_id, "", selected=not ref.variant_id
            )
        ]
        for v in variants:
            sku = str(v["sku"])
            label = _label(v) or f"SKU {sku}"
            price, _ = _prices(v)
            if price is not None:
                label += f": {_money(price)}"
            if v.get("stock") is not True:
                label += " (agotada)"
            out.append(
                Variant(
                    _url(ref.external_id, sku),
                    label,
                    ref.external_id,
                    sku,
                    selected=sku == ref.variant_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)


def _url(pid: str, sku: str = "") -> str:
    base = f"https://simple.ripley.cl/{pid}"
    return f"{base}?sku={sku}" if sku and _SKU_RE.match(sku) else base


def _product(raw: str) -> dict:
    m = _NEXT_RE.search(raw)
    if not m:
        raise FetchError("la página de Ripley no trae __NEXT_DATA__")
    try:
        data = json.loads(m.group(1))
    except ValueError as exc:
        raise FetchError("__NEXT_DATA__ de Ripley no es JSON") from exc
    props = (data.get("props") or {}).get("pageProps") or {}
    detail = props.get("detailProps")
    if not detail:
        # Categorías (/catalog/…), búsquedas (/search/…) y la página 404.
        raise NotFoundError(f"no es una ficha de producto (página {data.get('page')!r})")
    product = (detail.get("data") or {}).get("product")
    if not isinstance(product, dict) or not product.get("name"):
        raise FetchError("la ficha de Ripley no trae el producto")
    return product


def _variant(product: dict, sku: str) -> dict | None:
    return next((v for v in product.get("variants") or [] if str(v.get("sku")) == sku), None)


def _prices(source: dict) -> tuple[int | None, int | None]:
    prices = source.get("price") or {}

    def amount(kind: str) -> int | None:
        value = to_minor((prices.get(kind) or {}).get("valueNumber"), "CLP")
        return value if value else None  # 0 = no hay ese precio

    sale, master = amount("sale"), amount("master")
    price = sale if sale is not None else master
    return price, master if master and price is not None and master > price else None


def _label(variant: dict) -> str:
    """Valores de los atributos que definen la variante ("Blanco, M")."""
    values = []
    for attr in variant.get("attributes") or []:
        if attr.get("usage") != "Defining":
            continue
        values += [
            str(v.get("values")).strip() for v in attr.get("Values") or [] if v.get("values")
        ]
    return ", ".join(values)


def _image(product: dict) -> str | None:
    url = product.get("fullImage") or product.get("thumbnail")
    if not isinstance(url, str) or not url:
        return None
    return f"https:{url}" if url.startswith("//") else url


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
