"""Procesador de MercadoLibre Chile, vía API oficial (cuenta conectada en el panel admin).

El HTML de mercadolibre.cl tiene un challenge antibots propio que FlareSolverr no
resuelve, y la API no deja leer `/items` ni `/user-products` de otros vendedores. Lo
que sí es accesible es el **catálogo**: `/products/{id}` (nombre, fotos) y
`/products/{id}/items` (las publicaciones activas con precio). Por eso:

- Link de catálogo (`/p/MLC…`): se sigue el precio más bajo entre las publicaciones.
- Link de publicación (`/up/MLCU…`): se busca su catálogo con las palabras del link
  (una vez; queda en memoria) y se sigue esa publicación (por `user_product_id`).

La API no da la cantidad en stock: una oferta que deja de aparecer en
`/products/{id}/items` se trata como agotada (`sold_out_without_price`).
"""

import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

from tracker import meli
from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.util import to_minor

_HOSTS = {"mercadolibre.cl", "www.mercadolibre.cl"}
_CATALOG_RE = re.compile(r"/p/(MLC\d+)", re.I)
_UP_RE = re.compile(r"^/(?:([a-z0-9-]+)/)?up/(MLCU\d+)", re.I)
# Candidatos del catálogo que se revisan al buscar a qué catálogo pertenece una publicación.
_MAX_CANDIDATES = 20

# user_product_id → id de catálogo (se pierde al reiniciar; se vuelve a buscar).
_catalog_of: dict[str, str] = {}


class MercadoLibreProcessor(Processor):
    name = "mercadolibre"
    label = "MercadoLibre"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # Precios de la API: una caída grande es real, y "sin ofertas" es un agotado real.
    anomaly_drop_pct = None
    sold_out_without_price = True
    home_url = "https://www.mercadolibre.cl/"
    example_url = "https://www.mercadolibre.cl/p/MLC48419682"
    platform = "API de MercadoLibre"
    supports_list_price = True
    notes = (
        "Con un link de catálogo (/p/MLC…) se sigue el precio más bajo entre vendedores; "
        "con el de una publicación (/up/MLCU…), esa publicación. Requiere que el admin "
        "tenga MercadoLibre conectado."
    )

    def matches(self, url: str) -> bool:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return False
        if parts.hostname not in _HOSTS:
            return False
        return bool(_CATALOG_RE.search(parts.path) or _UP_RE.match(parts.path))

    def normalize(self, url: str) -> ProductRef:
        parts = urlsplit(url.strip())
        if parts.hostname not in _HOSTS:
            raise ValueError("no es una URL de MercadoLibre Chile")
        m = _CATALOG_RE.search(parts.path)
        if m:
            pid = m.group(1).upper()
            return ProductRef(pid, f"https://www.mercadolibre.cl/p/{pid}")
        m = _UP_RE.match(parts.path)
        if m:
            slug, up = (m.group(1) or "").lower(), m.group(2).upper()
            path = f"/{slug}/up/{up}" if slug else f"/up/{up}"
            return ProductRef(up, f"https://www.mercadolibre.cl{path}")
        raise ValueError("pega el link de un producto de MercadoLibre (/p/MLC… o /up/MLCU…)")

    def domain(self) -> str:
        return "api.mercadolibre.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        """JSON con el producto de catálogo y sus publicaciones (el `parse` es puro)."""
        try:
            if ref.external_id.startswith("MLCU"):
                catalog_id = await self._catalog_for(ref)
            else:
                catalog_id = ref.external_id
            product = await _get_json(f"/products/{catalog_id}")
            r = await meli.get(f"/products/{catalog_id}/items")
        except meli.MeliError as exc:
            raise FetchError(str(exc)) from exc
        if r.status_code == 404:
            items = []  # "No winners found": nadie lo vende ahora
        elif r.status_code == 200:
            items = r.json().get("results") or []
        else:
            raise FetchError(f"HTTP {r.status_code} en /products/{catalog_id}/items")
        return json.dumps(
            {"catalog_id": catalog_id, "product": product, "items": items}, ensure_ascii=False
        )

    async def _catalog_for(self, ref: ProductRef) -> str:
        up = ref.external_id
        if up in _catalog_of:
            return _catalog_of[up]
        slug = urlsplit(ref.canonical_url).path.split("/up/")[0].strip("/")
        terms = re.sub(r"-+", " ", slug).strip()
        if not terms:
            raise FetchError(
                "este link no trae el nombre del producto; usa el link del catálogo (/p/MLC…)"
            )
        r = await meli.get(
            "/products/search",
            {"status": "active", "site_id": "MLC", "q": terms, "limit": _MAX_CANDIDATES},
        )
        if r.status_code != 200:
            raise FetchError(f"HTTP {r.status_code} buscando en el catálogo")
        for cand in r.json().get("results") or []:
            ri = await meli.get(f"/products/{cand['id']}/items")
            if ri.status_code != 200:
                continue
            if any(i.get("user_product_id") == up for i in ri.json().get("results") or []):
                _catalog_of[up] = cand["id"]
                return cand["id"]
        raise NotFoundError(
            "no encontré esta publicación en el catálogo de MercadoLibre (puede estar agotada "
            "o no pertenecer a un catálogo); prueba con el link del catálogo (/p/MLC…)"
        )

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        data = json.loads(raw)
        product = data.get("product") or {}
        items = [i for i in data.get("items") or [] if i.get("currency_id", "CLP") == "CLP"]
        if ref.external_id.startswith("MLCU"):
            chosen = [i for i in items if i.get("user_product_id") == ref.external_id]
        else:
            chosen = items
        best = min(chosen, key=lambda i: i.get("price") or float("inf"), default=None)
        pictures = product.get("pictures") or []
        image = pictures[0].get("url") if pictures else None
        if best is None or best.get("price") is None:
            return ScrapeResult(
                title=product.get("name") or "",
                price=None,
                list_price=None,
                currency="CLP",
                available=False,
                image_url=image,
            )
        price = to_minor(best["price"], "CLP")
        original = best.get("original_price")
        list_price = to_minor(original, "CLP") if original and original > best["price"] else None
        return ScrapeResult(
            title=product.get("name") or "",
            price=price,
            list_price=list_price,
            currency="CLP",
            available=True,
            image_url=image,
        )


async def _get_json(path: str) -> dict:
    r = await meli.get(path)
    if r.status_code == 404:
        raise NotFoundError(f"{path} no existe en MercadoLibre")
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code} en {path}")
    return r.json()
