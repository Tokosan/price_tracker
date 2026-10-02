"""Procesador de Solotodo (solotodo.cl), comparador de precios de tiendas chilenas.

Usa la API pública oficial (sin clave), en dos llamadas:
- `/products/{id}/`: nombre e imagen; 404 si el producto no existe.
- `/products/available_entities/?ids={id}&countries=1`: las publicaciones ("entidades")
  de cada tienda, con su precio. Ojo: con un id inexistente este endpoint no filtra y
  devuelve todo el catálogo paginado, así que `parse` busca el resultado de su id.

`fetch_raw` junta las dos en `{"product": …, "available": …}`. El precio es el mínimo
`offer_price` entre las tiendas con stock (el precio con el medio de pago preferente,
normalmente transferencia, que es el que destaca la página). `normal_price` es el precio
con otros medios, no un precio "antes": no hay `list_price`.

El modo va en `variant_id` (y en `?modo=` de la URL), como en MercadoLibre: `""` (por
defecto) cuenta solo publicaciones nuevas; `todos` incluye reacondicionadas y usadas (lo mismo que
`exclude_refurbished=true` de la API: también deja fuera las usadas).
Se pide siempre todo y se filtra aquí, para mostrar los dos modos al agregar.
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

# /products/<id> o /products/<id>-<slug>; el slug no importa.
_URL_RE = re.compile(
    r"^https?://(?:www\.)?solotodo\.cl/products/(\d+)(?:-[^/?#]*)?/?(?:[?#].*)?$", re.I
)
API_URL = "https://publicapi.solotodo.com"
CHILE = 1  # id del país en la API (countries=1)
CLP = 1  # id de la moneda en la API (/currencies/1/ = CLP)
NEW = "https://schema.org/NewCondition"

# Modos (van en `variant_id` y en `?modo=` de la URL).
MODES = {
    "": "Solo nuevos",
    "todos": "Incluye reacondicionados y usados",
}


def offers(entities: list, mode: str) -> list[tuple[int, object]]:
    """(precio en CLP, tienda) de las publicaciones que cuenta cada modo."""
    out = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        registry = e.get("active_registry") or {}
        if not registry.get("is_available"):
            continue
        # Planes de celular y packs no son el producto suelto.
        if e.get("cell_plan") is not None or e.get("bundle") is not None:
            continue
        if e.get("currency") != CLP:
            continue
        if mode != "todos" and e.get("condition") != NEW:
            continue
        price = to_minor(registry.get("offer_price"), "CLP")
        if price is not None and price > 0:
            out.append((price, e.get("store")))
    return out


class SolotodoProcessor(Processor):
    name = "solotodo"
    label = "Solotodo"
    # La API cachea dos horas (cache-control: max-age=7200).
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # Sin publicaciones con stock = agotado real (la API deja de listarlas).
    sold_out_without_price = True
    home_url = "https://www.solotodo.cl/"
    example_url = "https://www.solotodo.cl/products/265617-a-data-legend-860-2-tb-sleg-860-2000gcs"
    platform = "API de Solotodo"
    supports_variants = True
    supports_list_price = False
    variants_title = "¿Qué ofertas considerar?"
    variants_hint = (
        "Solotodo compara varias tiendas y se sigue el precio más bajo. Cada opción se "
        "sigue por separado: marca las que quieras."
    )
    notes = (
        "Sigue el precio más bajo entre las tiendas que compara Solotodo (el precio por "
        "transferencia o el medio de pago preferente de cada tienda, no el precio con "
        "tarjeta). Por defecto solo cuenta productos nuevos; también puedes seguir el "
        "más barato incluidos los reacondicionados. No informa qué tienda lo tiene."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Solotodo")
        product_id = str(int(m.group(1)))
        mode = (parse_qs(urlsplit(url).query).get("modo") or [""])[0].lower()
        if mode not in MODES:
            mode = ""
        return ProductRef(product_id, _url(product_id, mode), mode)

    def domain(self) -> str:
        return "publicapi.solotodo.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        product = await get_text(f"{API_URL}/products/{ref.external_id}/")
        available = await get_text(
            f"{API_URL}/products/available_entities/",
            params={"ids": ref.external_id, "countries": CHILE},
        )
        # Texto crudo de cada respuesta, sin re-serializar.
        return f'{{"product": {product}, "available": {available}}}'

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product, entities = _load(raw, ref)
        price = min((p for p, _ in offers(entities, ref.variant_id)), default=None)
        return ScrapeResult(
            title=(product.get("name") or "").strip(),
            price=price,
            list_price=None,
            currency="CLP",
            available=price is not None,
            image_url=product.get("picture_url"),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Los dos modos con su precio de hoy (aunque uno no tenga ofertas)."""
        _, entities = _load(raw, ref)
        out: list[Variant] = []
        seen: set[tuple] = set()
        for mode, label in MODES.items():
            found = sorted(offers(entities, mode), key=lambda o: o[0])
            # Si "todos" cuenta lo mismo que "solo nuevos", no se ofrece (salvo que sea el del link).
            key = tuple(found)
            if key in seen and mode != ref.variant_id:
                continue
            seen.add(key)
            if found:
                n = len({store for _, store in found})
                stores = "1 tienda" if n == 1 else f"{n} tiendas"
                detail = f"${found[0][0]:,}".replace(",", ".") + f" ({stores})"
            else:
                detail = "sin ofertas hoy"
            out.append(
                Variant(
                    url=_url(ref.external_id, mode),
                    label=f"{label}: {detail}",
                    external_id=ref.external_id,
                    variant_id=mode,
                    selected=mode == ref.variant_id,
                )
            )
        return out

    def variant_label(self, external_id: str, variant_id: str) -> str:
        return MODES.get(variant_id, "")


def _url(product_id: str, mode: str) -> str:
    # Sin slug: solotodo.cl redirige /products/{id} a la URL con slug.
    return f"https://www.solotodo.cl/products/{product_id}" + (f"?modo={mode}" if mode else "")


def _load(raw: str, ref: ProductRef) -> tuple[dict, list]:
    """El producto y sus entidades; FetchError si la respuesta no es la esperada."""
    try:
        body = json.loads(raw, parse_float=Decimal)
    except ValueError as exc:
        raise FetchError("la API de Solotodo no devolvió JSON") from exc
    if not isinstance(body, dict):
        raise FetchError("respuesta inesperada de la API de Solotodo")
    product = body.get("product")
    available = body.get("available")
    if not isinstance(product, dict) or not isinstance(available, dict):
        raise FetchError("falta 'product' o 'available' en la respuesta de Solotodo")
    if "id" not in product and product.get("detail"):
        raise NotFoundError(f"Solotodo no tiene el producto {ref.external_id}")
    if str(product.get("id")) != ref.external_id:
        raise FetchError(f"la API devolvió otro producto ({product.get('id')!r})")
    # Un producto que existe aparece siempre en `results`, aunque sea sin entidades; si
    # no está, la respuesta no es confiable (no se toma como agotado).
    for result in available.get("results") or []:
        if not isinstance(result, dict):
            continue
        if str((result.get("product") or {}).get("id")) == ref.external_id:
            entities = result.get("entities")
            if not isinstance(entities, list):
                raise FetchError("faltan las entidades en la respuesta de Solotodo")
            return product, entities
    raise FetchError(f"available_entities no trae el producto {ref.external_id}")
