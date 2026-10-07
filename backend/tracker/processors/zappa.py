"""Procesador de Zappa (www.zappa.cl, calzado; PrestaShop con combinaciones por talla).

El precio, el título y la imagen salen del parseo común de `PrestaShopProcessor`, con dos
diferencias del tema de Zappa:

- `data-product.availability` vale `in_stock` (no `available`), y `quantity` es solo la de
  la talla por defecto. El stock por talla está en el `<select data-np-sc-map=…>` del
  selector de tallas: `{"<id del valor de talla>": {"qty": N, "available": bool}}`, con el
  nombre de cada talla en `<option value=… data-np-sc-name=…>`.
- El precio tachado no está en `.regular-price` sino en `data-product.price_without_reduction`
  (el precio sin la rebaja, `reduction`).

Cada color es su propio producto (otro `id_product`). La talla va en la URL como lo hace
PrestaShop, en el fragmento: `…/25588-zapato….html#/3-talla-36`, y en `variant_id` el id del
valor de talla (`3`). La ficha trae el stock de todas las tallas, así que basta una petición.
El precio por talla no viene en la ficha: se asume el mismo para todas (no se vio ninguna
combinación con otro precio).
"""

import html as htmllib
import json
import re

from tracker.processors.base import FetchError, NotFoundError, ProductRef, ScrapeResult, Variant
from tracker.processors.http import get_text
from tracker.processors.prestashop import PrestaShopProcessor, _data_product

_SIZE_FRAGMENT_RE = re.compile(r"(?:^|/)(\d+)-talla-([^/]+)", re.I)
_SELECT_RE = re.compile(r"<select[^>]*\bdata-np-sc-map=\"([^\"]*)\"[^>]*>(.*?)</select>", re.S)
_OPTION_RE = re.compile(r"<option[^>]*\bvalue=\"(\d+)\"[^>]*\bdata-np-sc-name=\"([^\"]*)\"", re.S)


class ZappaProcessor(PrestaShopProcessor):
    name = "zappa"
    label = "Zappa"
    host = "zappa.cl"
    canonical_host = "www.zappa.cl"
    home_url = "https://www.zappa.cl/"
    example_url = (
        "https://www.zappa.cl/producto/zapatos-mujer-cuero/"
        "25588-zapato-cuero-mujer-zam0223a01v0107.html"
    )
    supports_variants = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (con stock en alguna) o tallas puntuales, cada una "
        "por separado. Marca las que quieras."
    )
    notes = (
        'Precio de la ficha; el "antes" es el precio sin la rebaja. Cada color es un link '
        "distinto. Puedes seguir cualquier talla (disponible si queda alguna) o una talla "
        "puntual; todas las tallas tienen el mismo precio."
    )

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        ref = super().normalize(url)
        fragment = url.split("#", 1)[1] if "#" in url else ""
        m = _SIZE_FRAGMENT_RE.search(fragment)
        if not m:
            return ref
        size_id, size_name = m.group(1), m.group(2)
        return ProductRef(
            ref.external_id, _with_size(ref.canonical_url, size_id, size_name), size_id
        )

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("#", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        data = _data_product(raw)
        if not data:
            # Categorías y páginas de contenido no traen el data-product de la ficha.
            raise NotFoundError("no es una ficha de producto de Zappa")
        if str(data.get("id_product")) != ref.external_id:
            raise FetchError(f"la ficha es del producto {data.get('id_product')}")
        result = super().parse(raw, ref)
        normal = _int(data.get("price_without_reduction"))
        if normal and result.price is not None and normal > result.price:
            result.list_price = normal
        sizes = _sizes(raw)
        if ref.variant_id:
            size = sizes.get(ref.variant_id)
            # Una talla que ya no aparece en el selector no se puede comprar.
            result.available = bool(size and size["available"])
            name = size["name"] if size else ref.canonical_url.rsplit("-talla-", 1)[-1]
            result.title = f"{result.title} (talla {name})"
        elif sizes:
            result.available = any(s["available"] for s in sizes.values())
        else:
            quantity = _int(data.get("quantity_all_versions", data.get("quantity")))
            result.available = bool(quantity and quantity > 0)
        return result

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        sizes = _sizes(raw)
        if len(sizes) < 2:
            return []
        base = ref.canonical_url.split("#", 1)[0]
        out = [Variant(base, "Cualquier talla", ref.external_id, "", not ref.variant_id)]
        for size_id, size in sizes.items():
            label = f"Talla {size['name']}" + ("" if size["available"] else " (agotada)")
            url = _with_size(base, size_id, size["name"])
            out.append(Variant(url, label, ref.external_id, size_id, size_id == ref.variant_id))
        return sorted(out, key=lambda v: not v.selected)


def _with_size(url: str, size_id: str, size_name: str) -> str:
    slug = re.sub(r"[^a-z0-9.]+", "_", size_name.strip().lower()).strip("_") or size_id
    return f"{url.split('#', 1)[0]}#/{size_id}-talla-{slug}"


def _sizes(raw: str) -> dict[str, dict]:
    """{id del valor de talla: {name, available}} en el orden del selector."""
    m = _SELECT_RE.search(raw)
    if not m:
        return {}
    try:
        stock = json.loads(htmllib.unescape(m.group(1)))
    except ValueError:
        return {}
    if not isinstance(stock, dict):
        return {}
    out = {}
    for size_id, name in _OPTION_RE.findall(m.group(2)):
        info = stock.get(size_id) or {}
        qty = _int(info.get("qty"))
        out[size_id] = {
            "name": htmllib.unescape(name).strip(),
            "available": info.get("available") is True and bool(qty and qty > 0),
        }
    return out


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
