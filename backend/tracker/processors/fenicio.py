"""Base para tiendas de la plataforma Fenicio (Timberland, …; assets en `f.fcdn.app`).

Las fichas son HTML sin JSON-LD, en `/catalogo/<slug>_<codProducto>_<codVariante>`: cada
color (variante de Fenicio) tiene su propia URL, y las tallas se eligen en la misma ficha.
La ficha trae todo lo que hace falta, sin API aparte:

- `<div id="_jsonDataFicha_">` (oculto): JSON con `producto.codigo`, `variante.codigo`,
  `nombre` ("<producto> - <variante>"), `precioMonto` (precio de venta, entero en la
  moneda), `moneda.cod`, `variante.img.u` y `variante.tieneStock`.
- `.preciosWrapper`: el precio de venta (`strong.precio.venta .monto`) y, con descuento, el
  normal tachado (`del.precio.lista .monto`). Los productos relacionados usan otro bloque
  (`.cnt-precios`), así que el primer `preciosWrapper` es el de la ficha.
- `ul#lstTalles`: una `input[name=sku]` por talla con `value="1:<prod>:<var>:<talla>:1"`,
  `data-stock` (unidades) y `disabled` si está agotada.

`external_id` = `<codProducto>_<codVariante>`; `variant_id` = código de talla (el cuarto
campo del `value`), que va en la URL como `?talla=<código>` (Fenicio lo ignora). Sin talla
se sigue "cualquier talla": el precio de la ficha y disponible si queda alguna talla.

Subclases: `name`, `label`, `hosts`, `canonical_host` y los metadatos.
"""

import html as htmllib
import json
import re
from datetime import timedelta
from urllib.parse import parse_qs, quote, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import digits_to_int, exponent, to_minor

_JSON_RE = re.compile(r"<div[^>]*\bid=[\"']_jsonDataFicha_[\"'][^>]*>(.*?)</div>", re.S | re.I)
_LIST_PRICE_RE = re.compile(
    r"<del[^>]*class=[\"'][^\"']*\bprecio lista\b[^\"']*[\"'][^>]*>.*?"
    r"<span[^>]*class=[\"']monto[\"'][^>]*>([^<]+)<",
    re.S | re.I,
)
_SIZE_LIST_RE = re.compile(r"<ul[^>]*\bid=[\"']lstTalles[\"'][^>]*>(.*?)</ul>", re.S | re.I)
_SIZE_ITEM_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)
_INPUT_RE = re.compile(r"<input[^>]*\bname=[\"']sku[\"'][^>]*>", re.I)
_ATTR_RE = re.compile(r"([a-z-]+)(?:=(\"[^\"]*\"|'[^']*'))?", re.I)
_BOLD_RE = re.compile(r"<b>([^<]*)</b>", re.I)
_SIZE_CODE_RE = re.compile(r"^[A-Za-z0-9.,/-]{1,20}$")


class FenicioProcessor(Processor):
    """Subclases: `name`, `label`, `hosts`, `canonical_host` y los metadatos."""

    hosts: tuple[str, ...] = ()
    canonical_host: str = ""
    check_interval = timedelta(hours=6)
    platform = "Fenicio"
    supports_variants = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (con stock en alguna) o tallas puntuales, cada una "
        "por separado. Marca las que quieras."
    )

    def __init__(self) -> None:
        hosts = "|".join(re.escape(h) for h in self.hosts)
        # El slug puede traer guiones bajos: los códigos son los dos últimos segmentos.
        self._url_re = re.compile(
            rf"^https?://(?:{hosts})/catalogo/((?:[^/?#]*_)?)([A-Za-z0-9-]+)_([A-Za-z0-9-]+)"
            r"/?(?:[?#].*)?$",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = self._url_re.match(url)
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        slug = m.group(1).rstrip("_").lower()
        prod, var = m.group(2).upper(), m.group(3).upper()
        size = (parse_qs(urlsplit(url).query).get("talla") or [""])[0].strip()
        size = size if _SIZE_CODE_RE.match(size) else ""
        external_id = f"{prod}_{var}"
        return ProductRef(external_id, self._url(slug, external_id, size), size)

    def _url(self, slug: str, external_id: str, size: str = "") -> str:
        path = f"{slug}_{external_id}" if slug else external_id
        url = f"https://{self.canonical_host}/catalogo/{path}"
        return f"{url}?talla={quote(size, safe='')}" if size else url

    def domain(self) -> str:
        return self.canonical_host

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("?", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        data = _ficha(raw, ref)
        currency = ((data.get("moneda") or {}).get("cod") or "CLP").upper()
        price = to_minor(data.get("precioMonto"), currency)
        if not price:
            raise FetchError("la ficha no trae el precio (precioMonto)")
        title = htmllib.unescape(str(data.get("nombre") or "")).strip()
        sizes = _sizes(raw)
        if ref.variant_id:
            size = next((s for s in sizes if s["code"] == ref.variant_id), None)
            # Una talla que desaparece de la lista ya no se vende: agotada (con el precio
            # del color, que es el mismo para todas las tallas).
            available = bool(size and size["available"])
            label = size["label"] if size else ref.variant_id
            title = f"{title} (talla {label})"
        elif sizes:
            available = any(s["available"] for s in sizes)
        else:
            available = (data.get("variante") or {}).get("tieneStock") is True
        return ScrapeResult(
            title=title,
            price=price,
            list_price=_list_price(raw, price, currency),
            currency=currency,
            available=available,
            image_url=_image(data),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """ "Cualquier talla" (el link sin talla) y cada talla de la ficha."""
        _ficha(raw, ref)
        sizes = _sizes(raw)
        if len(sizes) < 2:
            return []
        slug = _slug(ref.canonical_url)
        out = [
            Variant(
                self._url(slug, ref.external_id),
                "Cualquier talla",
                ref.external_id,
                "",
                selected=not ref.variant_id,
            )
        ]
        for s in sizes:
            label = f"Talla {s['label']}" + ("" if s["available"] else " (agotada)")
            out.append(
                Variant(
                    self._url(slug, ref.external_id, s["code"]),
                    label,
                    ref.external_id,
                    s["code"],
                    selected=s["code"] == ref.variant_id,
                )
            )
        return sorted(out, key=lambda v: not v.selected)


def _ficha(raw: str, ref: ProductRef) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        # Categorías, búsquedas y páginas de contenido no traen el JSON de la ficha.
        raise NotFoundError("no es una ficha de producto (sin _jsonDataFicha_)")
    try:
        data = json.loads(htmllib.unescape(m.group(1).strip()))
    except ValueError as exc:
        raise FetchError("el JSON de la ficha no es válido") from exc
    if not isinstance(data, dict):
        raise FetchError("el JSON de la ficha no es un objeto")
    prod = str((data.get("producto") or {}).get("codigo") or "").upper()
    var = str((data.get("variante") or {}).get("codigo") or "").upper()
    if f"{prod}_{var}" != ref.external_id:
        raise FetchError(f"la ficha es de {prod}_{var}, no de {ref.external_id}")
    return data


def _sizes(raw: str) -> list[dict]:
    """Tallas de `#lstTalles`: [{code, label, available}] en el orden de la ficha."""
    m = _SIZE_LIST_RE.search(raw)
    if not m:
        return []
    out = []
    for item in _SIZE_ITEM_RE.finditer(m.group(1)):
        tag = _INPUT_RE.search(item.group(1))
        if not tag:
            continue
        attrs = {
            k.lower(): htmllib.unescape(v[1:-1]) if v else ""
            for k, v in _ATTR_RE.findall(tag.group(0)[len("<input") :])
        }
        parts = attrs.get("value", "").split(":")
        if len(parts) < 4 or not parts[3]:
            continue
        stock = attrs.get("data-stock", "")
        available = "disabled" not in attrs and not (stock.isdigit() and int(stock) == 0)
        bold = _BOLD_RE.search(item.group(1))
        label = htmllib.unescape(bold.group(1)).strip() if bold else parts[3]
        out.append({"code": parts[3], "label": label or parts[3], "available": available})
    return out


def _list_price(raw: str, price: int, currency: str) -> int | None:
    start = raw.find("preciosWrapper")
    if start < 0 or exponent(currency) != 0:
        return None
    end = raw.find("_jsonDataFicha_", start)
    m = _LIST_PRICE_RE.search(raw, start, end if end > start else start + 2000)
    if not m:
        return None
    normal = digits_to_int(htmllib.unescape(m.group(1)))
    return normal if normal and normal > price else None


def _image(data: dict) -> str | None:
    url = ((data.get("variante") or {}).get("img") or {}).get("u")
    if not isinstance(url, str) or not url:
        return None
    return f"https:{url}" if url.startswith("//") else url


def _slug(canonical_url: str) -> str:
    path = urlsplit(canonical_url).path.rsplit("/", 1)[-1]
    parts = path.split("_")
    return "_".join(parts[:-2]) if len(parts) > 2 else ""
