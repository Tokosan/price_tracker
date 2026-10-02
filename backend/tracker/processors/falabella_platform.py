"""Base para las tiendas de la plataforma Falabella (Falabella, y luego Sodimac y Tottus).

Las fichas HTML dan 403 de Cloudflare, pero la API de browse no:
`GET https://www.falabella.com/s/browse/v3/product/cl?site=<site>&productId=<pid>`.
`site` tiene que ir antes de `productId` (en el otro orden responde 302). La API vive
solo en falabella.com, también para las otras tiendas del grupo.

La respuesta trae el producto con sus variantes (tallas, colores, medidas), cada una
con su SKU, sus precios y si se puede comprar:

- `responseType == "NOT_FOUND"` (HTTP 200, `data: {}`) → `NotFoundError`.
- `responseType == "OUT_OF_STOCK"` → todo agotado. Si además no hay variantes, tampoco
  hay precio: es un agotado real (`sold_out_without_price`).
- `prices[]`: `{type, price: ["1.629.990"], crossed}`. `price` = `eventPrice` o, si no,
  `internetPrice`; `list_price` = `normalPrice` tachado. `cmrPrice` (tarjeta CMR) se ignora.
- Stock por variante: `isPurchaseable` (falta cuando está agotada). `availability[]` no sirve.

URL: `/<site>/<product|articulo>/<pid>[/<slug>[/<sku>]]`. `external_id` = pid y
`variant_id` = sku (o `""` si el link no lo trae: se sigue `currentVariant`).
"""

import json
import re
from datetime import timedelta

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import digits_to_int

API_URL = "https://www.falabella.com/s/browse/v3/product/cl"
_KNOWN_RESPONSE_TYPES = {None, "OUT_OF_STOCK"}


class FalabellaPlatformProcessor(Processor):
    """Subclases: `name`, `label`, `hosts`, `canonical_host`, `site`, `path_kind`.

    `extra_params` se agrega a la query de la API (p. ej. zonas de despacho).
    """

    hosts: tuple[str, ...] = ()
    canonical_host: str = ""
    site: str = ""  # falabella-cl, sodimac-cl, tottus-cl
    path_kind: str = "product"  # "product" en Falabella, "articulo" en Sodimac y Tottus
    extra_params: tuple[tuple[str, str], ...] = ()

    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # API no oficial: se mantiene el control de caídas. Sin variantes = agotado real.
    sold_out_without_price = True
    platform = "Falabella"
    supports_variants = True
    variants_hint = (
        "Cada talla, color o medida tiene su propio precio y stock. Marca las que quieras."
    )

    def __init__(self) -> None:
        hosts = "|".join(re.escape(h) for h in self.hosts)
        self._url_re = re.compile(
            rf"^https?://(?:{hosts})/{re.escape(self.site)}/{re.escape(self.path_kind)}"
            r"/(\d+)(?:/([^/?#]+)(?:/(\d+))?)?/?(?:[?#].*)?$",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = self._url_re.match(url.strip())
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        pid, slug, sku = m.group(1), m.group(2) or "", m.group(3) or ""
        return ProductRef(pid, self._url(pid, slug, sku), sku)

    def _url(self, pid: str, slug: str = "", sku: str = "") -> str:
        url = f"https://{self.canonical_host}/{self.site}/{self.path_kind}/{pid}"
        if slug:
            url += f"/{slug}"
            if sku:
                url += f"/{sku}"
        return url

    def domain(self) -> str:
        return "www.falabella.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        # El orden importa: `site` antes de `productId`.
        params = {"site": self.site, "productId": ref.external_id, **dict(self.extra_params)}
        return await get_text(API_URL, params=params)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        response, data = _load(raw)
        sold_out = response == "OUT_OF_STOCK"
        variants = data.get("variants") or []
        v = _pick(data, ref.variant_id)
        if v is None:
            # Agotado real: la API lo dice, o el SKU del link ya no está entre las demás
            # variantes (talla descontinuada). Sin variantes y sin decirlo, es un error.
            if not sold_out and not (ref.variant_id and variants):
                raise FetchError("la respuesta no trae la variante y no dice que esté agotado")
            return ScrapeResult(data.get("name") or "", None, None, "CLP", False, None)
        price, list_price = _prices(v)
        title = data.get("name") or v.get("name") or ""
        label = _label(v)
        if len(variants) > 1 and label:
            title = f"{title} ({label})"
        medias = v.get("medias") or data.get("medias") or []
        return ScrapeResult(
            title=title.strip(),
            price=price,
            list_price=list_price,
            currency="CLP",
            available=not sold_out and v.get("isPurchaseable") is True,
            image_url=medias[0].get("url") if medias else None,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las variantes hermanas, cada una con su SKU en la URL.

        La que corresponde al link actual conserva su URL si el link trae SKU. Si no lo
        trae, se devuelve con el SKU de `currentVariant`: al agregarla se sigue esa
        variante fija, y no la que la ficha muestre más adelante (que puede cambiar, y en
        Sodimac las medidas tienen precios distintos).
        """
        _, data = _load(raw)
        variants = data.get("variants") or []
        if len(variants) < 2:
            return []
        current = _pick(data, ref.variant_id)
        current_id = str(current.get("id")) if current else None
        slug = data.get("slug") or "p"
        out: list[Variant] = []
        for v in variants:
            vid = str(v.get("id") or "")
            if not vid:
                continue
            label = _label(v) or v.get("name") or vid
            price, _ = _prices(v)
            if price is not None:
                label += f": ${price:,}".replace(",", ".")
            if v.get("isPurchaseable") is not True:
                label += " (agotada)"
            if vid == current_id and ref.variant_id:
                out.append(Variant(ref.canonical_url, label, ref.external_id, vid, True))
            else:
                url = self._url(ref.external_id, slug, vid)
                out.append(Variant(url, label, ref.external_id, vid, vid == current_id))
        return sorted(out, key=lambda v: not v.selected)


def _load(raw: str) -> tuple[str | None, dict]:
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise FetchError("la API no devolvió JSON") from exc
    response = body.get("responseType")
    if response == "NOT_FOUND":
        raise NotFoundError("el producto no existe")
    if response not in _KNOWN_RESPONSE_TYPES:
        raise FetchError(f"respuesta desconocida de la API: {response}")
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        raise FetchError("la respuesta no trae el producto")
    return response, data


def _pick(data: dict, variant_id: str) -> dict | None:
    """La variante del SKU pedido o, sin SKU, la que muestra la ficha (`currentVariant`)."""
    wanted = variant_id or str(data.get("currentVariant") or "")
    variants = data.get("variants") or []
    found = next((v for v in variants if str(v.get("id")) == wanted), None)
    if found is None and not variant_id and len(variants) == 1:
        return variants[0]
    return found


def _prices(v: dict) -> tuple[int | None, int | None]:
    by_type: dict[str, dict] = {p.get("type"): p for p in v.get("prices") or []}

    def amount(kind: str) -> int | None:
        values = (by_type.get(kind) or {}).get("price") or []
        return digits_to_int(values[0]) if values else None

    price = amount("eventPrice") or amount("internetPrice")
    normal = amount("normalPrice")
    if price is None and not (by_type.get("normalPrice") or {}).get("crossed"):
        price = normal  # sin precio internet, el normal es el que paga cualquiera
    crossed = (by_type.get("normalPrice") or {}).get("crossed")
    list_price = normal if crossed and normal and price is not None and normal > price else None
    return price, list_price


def _label(v: dict) -> str:
    attrs = v.get("attributes") or {}
    parts = [attrs.get("colorName"), attrs.get("size")]
    return " · ".join(str(p).strip() for p in parts if p and str(p).strip())
