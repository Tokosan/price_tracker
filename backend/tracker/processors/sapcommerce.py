"""Base para tiendas sobre SAP Commerce (Hybris) con la API OCC (Bold, Belsport, …).

El front es una SPA (Spartacus, Angular) cuyo HTML no trae el producto: los datos salen de
la API OCC pública que usa el propio front, sin autenticación:
`GET <api>/rest/v2/<baseSite>/products/<código>?fields=FULL`.

- Código inexistente: HTTP 400 con `errors[].type == "UnknownIdentifierError"`.
- Producto base (p. ej. `ADJR1121`): `price`/`regularPrice` ("FROM") y `variantOptions[]`,
  una por talla, con su `code`, `priceData`, `regularPrice`, `stock.stockLevelStatus`
  (`inStock`, `lowStock`, `outOfStock`), `url` y la talla en `variantOptionQualifiers`.
  El `stock` del base no sirve (dice `outOfStock` con tallas disponibles): el front lo
  calcula como "alguna talla no está `outOfStock`", y aquí se hace igual.
- Talla (p. ej. `ADJR1121080`): un producto con `baseProduct`, su propio `stock` y sus
  hermanas en `baseOptions[0].options`.
- `physicalStockLevelStatus` / `physicalStockLevelByZone` es el stock de las tiendas
  físicas: el front no lo usa para vender online, así que se ignora.

URL de la ficha: `/<categorías>/<slug>/p/<código>`. `external_id` = código: cada talla es
su propio producto (su link es el del código de talla), y el código base sigue
"cualquier talla" (el precio más bajo entre las tallas con stock).

Subclases: `name`, `label`, `hosts`, `canonical_host`, `api_base`, `base_site`.
"""

import html as htmllib
import json
import re
from datetime import timedelta
from urllib.parse import quote, urlsplit

import httpx

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import USER_AGENT
from tracker.processors.util import to_minor

_TAG_RE = re.compile(r"<[^>]+>")
_OUT = "outOfStock"


class SapCommerceProcessor(Processor):
    """Subclases: `name`, `label`, `hosts`, `canonical_host`, `api_base`, `base_site`."""

    hosts: tuple[str, ...] = ()
    canonical_host: str = ""
    api_base: str = ""  # https://<host>/rest/v2
    base_site: str = ""
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    platform = "SAP Commerce (API OCC)"
    supports_variants = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (el precio más bajo, con stock en alguna) o tallas "
        "puntuales, cada una por separado. Marca las que quieras."
    )

    def __init__(self) -> None:
        hosts = "|".join(re.escape(h) for h in self.hosts)
        self._url_re = re.compile(
            rf"^https?://(?:{hosts})((?:/[^/?#]+)*?/p/([A-Za-z0-9_-]+))/?(?:[?#].*)?$",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = self._url_re.match(url.strip())
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        code = m.group(2).upper()
        path = m.group(1)[: -len(m.group(2))] + code
        return ProductRef(code, f"https://{self.canonical_host}{path}")

    def domain(self) -> str:
        return urlsplit(self.api_base).hostname or self.canonical_host

    def api_url(self, code: str) -> str:
        return f"{self.api_base}/{self.base_site}/products/{quote(code, safe='')}"

    async def fetch_raw(self, ref: ProductRef) -> str:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(headers=headers, timeout=30) as client:
                resp = await client.get(self.api_url(ref.external_id), params={"fields": "FULL"})
        except httpx.HTTPError as exc:
            raise FetchError(f"error de red: {exc!r}") from exc
        if resp.status_code in (400, 404) and "UnknownIdentifierError" in resp.text:
            raise NotFoundError(f"{ref.external_id} no existe en {self.label}")
        if resp.status_code >= 400:
            raise FetchError(f"HTTP {resp.status_code} en la API de {self.label}")
        return resp.text

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = self._load(raw, ref)
        title = _clean(product.get("name"))
        options = _options(product.get("variantOptions"))
        if options:
            # Producto base: cualquier talla, como lo calcula el front.
            in_stock = [o for o in options if _in_stock(o)]
            chosen = min(in_stock or options, key=lambda o: _amount(o.get("priceData")) or 10**15)
            price = _amount(chosen.get("priceData"))
            regular = _amount(chosen.get("regularPrice"))
            available = bool(in_stock)
        else:
            price = _amount(product.get("price"))
            regular = _amount(product.get("regularPrice"))
            stock = (product.get("stock") or {}).get("stockLevelStatus")
            if not isinstance(stock, str):
                raise FetchError("la API no trae stock.stockLevelStatus")
            available = stock != _OUT
            size = _size(_find(_siblings(product), ref.external_id))
            if product.get("baseProduct") and size:
                title = f"{title} (talla {size})"
        if not price:
            raise FetchError("la API no trae el precio")
        return ScrapeResult(
            title=title,
            price=price,
            list_price=regular if regular and regular > price else None,
            currency=_currency(product),
            available=available,
            image_url=self._image(product),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """ "Cualquier talla" (el código base) y cada talla (su propio código)."""
        product = self._load(raw, ref)
        base_code = str(product.get("baseProduct") or "") or ref.external_id
        options = _options(product.get("variantOptions")) or _siblings(product)
        if len(options) < 2:
            return []
        base_url = re.sub(
            r"/p/[^/]+$", f"/p/{quote(base_code, safe='')}", ref.canonical_url, flags=re.I
        )
        out = [
            Variant(
                base_url,
                "Cualquier talla",
                base_code,
                "",
                selected=ref.external_id == base_code,
            )
        ]
        for o in options:
            code = str(o.get("code") or "")
            url = o.get("url")
            if not code or not isinstance(url, str) or not self.matches(self._abs(url)):
                continue
            label = f"Talla {_size(o) or code}"
            price = _amount(o.get("priceData"))
            if price:
                label += f": ${price:,}".replace(",", ".")
            if not _in_stock(o):
                label += " (agotada)"
            out.append(
                Variant(
                    self.normalize(self._abs(url)).canonical_url,
                    label,
                    code.upper(),
                    "",
                    selected=code.upper() == ref.external_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)

    def _abs(self, path: str) -> str:
        return f"https://{self.canonical_host}{path}" if path.startswith("/") else path

    def _image(self, product: dict) -> str | None:
        images = [i for i in product.get("images") or [] if isinstance(i, dict)]
        primary = [i for i in images if i.get("imageType") == "PRIMARY"] or images
        by_format = {i.get("format"): i.get("url") for i in primary}
        url = by_format.get("product") or by_format.get("zoom") or by_format.get("superZoom")
        if not isinstance(url, str) or not url:
            return None
        if url.startswith("/"):
            parts = urlsplit(self.api_base)
            return f"{parts.scheme}://{parts.netloc}{url}"
        return url

    def _load(self, raw: str, ref: ProductRef) -> dict:
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError(f"la API de {self.label} no devolvió JSON") from exc
        if not isinstance(data, dict):
            raise FetchError(f"respuesta inesperada de la API de {self.label}")
        errors = data.get("errors") or []
        if any(isinstance(e, dict) and e.get("type") == "UnknownIdentifierError" for e in errors):
            raise NotFoundError(f"{ref.external_id} no existe en {self.label}")
        if errors or str(data.get("code") or "").upper() != ref.external_id:
            raise FetchError(f"la API de {self.label} no devolvió el producto pedido")
        return data


def _options(value) -> list[dict]:
    return [o for o in value or [] if isinstance(o, dict) and o.get("code")]


def _siblings(product: dict) -> list[dict]:
    base_options = product.get("baseOptions") or []
    if base_options and isinstance(base_options[0], dict):
        return _options(base_options[0].get("options"))
    return []


def _find(options: list[dict], code: str) -> dict:
    return next((o for o in options if str(o.get("code")).upper() == code), {})


def _in_stock(option: dict) -> bool:
    status = (option.get("stock") or {}).get("stockLevelStatus")
    return isinstance(status, str) and status != _OUT


def _amount(price) -> int | None:
    if not isinstance(price, dict):
        return None
    return to_minor(price.get("value"), price.get("currencyIso") or "CLP") or None


def _currency(product: dict) -> str:
    return str((product.get("price") or {}).get("currencyIso") or "CLP").upper()


def _size(option: dict) -> str:
    for q in option.get("variantOptionQualifiers") or []:
        if isinstance(q, dict) and q.get("value"):
            return str(q["value"]).strip()
    return ""


def _clean(name) -> str:
    return " ".join(htmllib.unescape(_TAG_RE.sub("", str(name or ""))).split())
