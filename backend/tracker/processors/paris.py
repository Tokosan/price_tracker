"""Procesador de Paris (paris.cl), vía la API de commercetools que usa el front.

La ficha es Next.js sobre commercetools; el JSON-LD no sirve (trae ofertas sin
etiqueta y sin stock). Se usan dos llamadas de `be-paris-backend-cl-ms-api`:

- `/products/by-key/{key}`: nombre, variantes (cada una con su SKU) y precios
  (`regular`, `offer` y `paymentMethod`, que es el de la Tarjeta Cencosud y se ignora).
  404 `ProductNotFound` si no existe.
- `/products/serviceability/by-skus?skusList=…&locality=13114`: stock por SKU
  (`isServiceable`) para Las Condes, la comuna por defecto del front. El stock cambia
  según la comuna; el precio no. Un SKU que no existe también sale `isServiceable: false`,
  por eso la existencia la decide `by-key`.

`fetch_raw` junta las dos en un JSON `{"product": …, "serviceability": …}`. El servidor
responde siempre con brotli, aunque no se le pida (hace falta `httpx[brotli]`).

Las variantes (tallas, colores) comparten la URL de la ficha: la que se sigue va en
`variant_id` y en `?sku=` de la URL (sin SKU, la `masterVariant`).
"""

import json
import re
from datetime import timedelta
from decimal import Decimal
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

API_URL = "https://be-paris-backend-cl-ms-api.ccom.paris.cl/products"
LOCALITY = "13114"  # Las Condes, la comuna por defecto del front
_HOSTS = {"www.paris.cl", "paris.cl"}
# /<slug>-<key>.html; la key es lo que va después del último guion (855637, MKTDEDRP8J).
_PATH_RE = re.compile(r"^/([A-Za-z0-9-]+)-([A-Za-z0-9]+)\.html$")
_SKU_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
# Atributos que distinguen una variante de otra, en el orden en que se muestran.
_LABEL_ATTRS = ("color", "size")


class ParisProcessor(Processor):
    name = "paris"
    label = "Paris"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    home_url = "https://www.paris.cl/"
    example_url = "https://www.paris.cl/rack-tv-65-elegant-394782.html"
    platform = "API de Paris (commercetools)"
    supports_variants = True
    supports_list_price = True
    variants_hint = (
        "Cada talla o color tiene su propio stock. Cada opción se sigue por separado: "
        "marca las que quieras."
    )
    notes = (
        'Precio oferta (o el normal, si no hay oferta), sin la Tarjeta Cencosud. El "antes" '
        "es el precio normal. El stock es el de despacho en Las Condes (la comuna por "
        "defecto del sitio): puede cambiar según la comuna, el precio no. Incluye productos "
        "de vendedores externos (marketplace)."
    )

    def matches(self, url: str) -> bool:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return False
        return (parts.hostname or "") in _HOSTS and bool(_PATH_RE.match(parts.path))

    def normalize(self, url: str) -> ProductRef:
        parts = urlsplit(url.strip())
        m = _PATH_RE.match(parts.path)
        if (parts.hostname or "") not in _HOSTS or not m:
            raise ValueError("no es una URL de producto de Paris")
        key = m.group(2)
        sku = (parse_qs(parts.query).get("sku") or [""])[0].strip()
        if not _SKU_RE.match(sku):
            sku = ""
        return ProductRef(key, _url(m.group(1), key, sku), sku)

    def domain(self) -> str:
        return "be-paris-backend-cl-ms-api.ccom.paris.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        product = await get_text(f"{API_URL}/by-key/{ref.external_id}")
        try:
            skus = [v["sku"] for v in _variants(json.loads(product))]
        except (ValueError, KeyError, TypeError) as exc:
            raise FetchError("la API de Paris devolvió un producto sin variantes") from exc
        serviceability = await get_text(
            f"{API_URL}/serviceability/by-skus",
            params={"skusList": ",".join(skus), "locality": LOCALITY},
        )
        # Texto crudo de cada respuesta, sin re-serializar.
        return f'{{"product": {product}, "serviceability": {serviceability}}}'

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product, stock = _load(raw)
        variants = _variants(product)
        v = _pick(variants, ref.variant_id)
        if v is None:
            raise NotFoundError(f"Paris ya no tiene la variante {ref.variant_id}")
        if v.get("sku") not in stock:
            raise FetchError(f"falta el stock del SKU {v.get('sku')} en la respuesta")
        price, list_price = _prices(v)
        title = _localized(product.get("name"))
        label = _label(v, variants)
        if len(variants) > 1 and label:
            title = f"{title} ({label})"
        images = v.get("images") or []
        return ScrapeResult(
            title=title.strip(),
            price=price,
            list_price=list_price,
            currency="CLP",
            available=stock[v["sku"]],
            image_url=images[0].get("url") if images else None,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las variantes del producto, cada una con su SKU en `?sku=` de la URL.

        Con un link sin SKU, la actual (`masterVariant`) también sale con su SKU, para que
        el producto que se agrega siga una variante fija. Con una sola variante es al revés:
        se devuelve sin SKU (`variant_id` vacío).
        """
        product, stock = _load(raw)
        variants = _variants(product)
        m = _PATH_RE.match(urlsplit(ref.canonical_url).path)
        slug = m.group(1) if m else ref.external_id
        if len(variants) == 1:
            # Una sola variante: el `?sku=` del link no aporta nada. Se ofrece la forma sin
            # SKU (la UI no muestra selector con una opción, pero agrega esta URL), para que
            # el link limpio y el compartido desde el sitio, con `?sku=`, sean el mismo Product.
            if _pick(variants, ref.variant_id) is None:
                raise NotFoundError(f"Paris ya no tiene la variante {ref.variant_id}")
            return [Variant(_url(slug, ref.external_id), "", ref.external_id, "", True)]
        current = _pick(variants, ref.variant_id)
        current_sku = current.get("sku") if current else None
        out: list[Variant] = []
        for v in variants:
            sku = v.get("sku") or ""
            if not _SKU_RE.match(sku):
                continue
            label = _label(v, variants) or sku
            price, _ = _prices(v)
            if price is not None:
                label += f": ${price:,}".replace(",", ".")
            if not stock.get(sku):
                label += " (agotada)"
            url = _url(slug, ref.external_id, sku)
            if sku == current_sku and ref.variant_id:
                url = ref.canonical_url
            out.append(Variant(url, label, ref.external_id, sku, sku == current_sku))
        return sorted(out, key=lambda v: not v.selected)


def _url(slug: str, key: str, sku: str = "") -> str:
    url = f"https://www.paris.cl/{slug}-{key}.html"
    return f"{url}?sku={sku}" if sku else url


def _load(raw: str) -> tuple[dict, dict[str, bool]]:
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise FetchError("la API de Paris no devolvió JSON") from exc
    product = body.get("product") if isinstance(body, dict) else None
    if not isinstance(product, dict):
        raise FetchError("falta el producto en la respuesta de Paris")
    if product.get("statusCode") == 404:
        raise NotFoundError("Paris no tiene ese producto")
    if not isinstance(product.get("masterVariant"), dict):
        raise FetchError("la respuesta de Paris no trae variantes")
    items = (body.get("serviceability") or {}).get("itemsServiceability")
    if not isinstance(items, list):
        raise FetchError("falta el stock en la respuesta de Paris")
    stock = {
        i["sku"]: i.get("isServiceable") is True
        for i in items
        if isinstance(i, dict) and i.get("sku")
    }
    return product, stock


def _variants(product: dict) -> list[dict]:
    return [product["masterVariant"], *(product.get("variants") or [])]


def _pick(variants: list[dict], sku: str) -> dict | None:
    if not sku:
        return variants[0]  # masterVariant
    return next((v for v in variants if v.get("sku") == sku), None)


def _amount(price: dict | None) -> int | None:
    value = (price or {}).get("value") or {}
    if value.get("currencyCode") != "CLP" or value.get("centAmount") is None:
        return None
    cents = Decimal(value["centAmount"]).scaleb(-int(value.get("fractionDigits") or 0))
    return to_minor(cents, "CLP")


def _prices(v: dict) -> tuple[int | None, int | None]:
    prices = v.get("prices") or {}
    regular = _amount(prices.get("regular"))
    offer = _amount(prices.get("offer"))
    price = offer or regular  # `paymentMethod` (Tarjeta Cencosud) se ignora
    if price is not None and price <= 0:
        price = None  # un precio en cero es un dato roto, no una oferta
    list_price = regular if regular and price is not None and regular > price else None
    return price, list_price


def _attrs(v: dict) -> dict:
    return {a.get("name"): a.get("value") for a in v.get("attributes") or [] if isinstance(a, dict)}


def _label(v: dict, variants: list[dict]) -> str:
    """Los atributos (color, talla) que cambian entre las variantes del producto."""
    attrs = _attrs(v)
    others = [_attrs(o) for o in variants]
    parts = []
    for name in _LABEL_ATTRS:
        value = attrs.get(name)
        varies = len({str(o.get(name)) for o in others}) > 1
        if isinstance(value, str) and value.strip() and varies:
            # "CL 39 | US 7.5 | 40.5 EU | …": basta la talla chilena.
            parts.append(value.split("|")[0].strip())
    return " · ".join(parts)


def _localized(value: object) -> str:
    if isinstance(value, dict):
        return value.get("es-CL") or next(iter(value.values()), "") or ""
    return value if isinstance(value, str) else ""
