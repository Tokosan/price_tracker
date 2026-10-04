"""Procesador de Liga Farmacia (ligafarmacia.cl, farmacia de la Liga Chilena contra la
Epilepsia).

La web es una SPA de React sobre Firebase: el HTML no trae datos. El front carga el
catálogo completo de un documento público de Firestore (sin login ni API key):
`publico_test/new_presku02`, la modalidad por defecto del sitio ("Despacho a domicilio
Santiago"; las otras, `new_presku03`…, son retiro por sede). `fields.sku` es un arreglo
de ~1.100 productos (~4 MB) con los valores tipados de Firestore (`stringValue`,
`integerValue` como string, `booleanValue`…). Las fotos van en otro documento público,
`publico/fotos_medicamentos_new` (`fields.images_med`: `{kinf2, kinf, image: [rutas]}`),
que el front cruza por `kinf2`.

Para no bajar ~5 MB por producto en cada ronda, los dos documentos se guardan en una caché
en memoria del proceso con TTL corto, bajo un lock: los productos de la tienda que se
revisan en el mismo tick hacen una sola descarga. `fetch_raw` devuelve solo lo del
producto, `{"producto": {…} | null, "imagen": "<ruta>" | null}`, así `parse` queda puro y
las fixtures son chicas.

La ficha (`/product/<kinf2>-<slug>`) solo usa lo que va antes del primer guion: el slug no
importa y `/product/<kinf2>` abre la misma ficha. Muestra `precio_con_dscto` y, si es
menor, `precio` tachado. "Añadir al carro" aparece si `comercio_elec` y hay `stock`; con
`comercio_elec` en false dice "Sólo venta presencial" (no se puede comprar online) y con
stock 0, "Sin stock".
"""

import asyncio
import json
import re
import time
from datetime import timedelta
from urllib.parse import urlsplit

from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import get_text

_HOSTS = frozenset({"ligafarmacia.cl", "www.ligafarmacia.cl"})
# /product/<kinf2> o /product/<kinf2>-<slug>; kinf2 son 9 dígitos.
_PATH_RE = re.compile(r"^/product/(\d{9})(?:-[^/]*)?/?$")
SITE_URL = "https://ligafarmacia.cl"
FIRESTORE_URL = (
    "https://firestore.googleapis.com/v1/projects/farmstore-744f9/databases/(default)/documents"
)
CATALOG_URL = f"{FIRESTORE_URL}/publico_test/new_presku02"
IMAGES_URL = f"{FIRESTORE_URL}/publico/fotos_medicamentos_new"
CACHE_TTL = 600  # segundos

# (momento de la descarga, productos por kinf2, primera foto por kinf2). None = sin caché.
_cache: tuple[float, dict[str, dict], dict[str, str]] | None = None
_cache_lock = asyncio.Lock()


class LigaFarmaciaProcessor(Processor):
    name = "ligafarmacia"
    label = "Liga Farmacia"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    home_url = "https://ligafarmacia.cl/"
    example_url = "https://ligafarmacia.cl/product/007640030-neuroval-cd-10-mg"
    platform = "Firebase (catálogo público en Firestore)"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio y stock de la modalidad «Despacho a domicilio Santiago». Los medicamentos "
        "de «Sólo venta presencial» figuran como no disponibles. Los de receta médica "
        "retenida requieren la receta al comprar."
    )

    def _kinf2(self, url: str) -> str | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS:
            return None
        m = _PATH_RE.match(parts.path)
        return m.group(1) if m else None

    def matches(self, url: str) -> bool:
        return self._kinf2(url) is not None

    def normalize(self, url: str) -> ProductRef:
        kinf2 = self._kinf2(url)
        if not kinf2:
            raise ValueError("no es una URL de producto de Liga Farmacia")
        return ProductRef(kinf2, f"{SITE_URL}/product/{kinf2}")

    def domain(self) -> str:
        return "ligafarmacia.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        products, images = await _catalog()
        return json.dumps(
            {"producto": products.get(ref.external_id), "imagen": images.get(ref.external_id)},
            ensure_ascii=False,
        )

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("la respuesta de Liga Farmacia no es JSON") from exc
        if not isinstance(body, dict) or "producto" not in body:
            raise FetchError("respuesta inesperada de Liga Farmacia")
        product = body["producto"]
        if product is None:
            raise NotFoundError(f"Liga Farmacia no tiene el producto {ref.external_id}")
        if not isinstance(product, dict):
            raise FetchError("respuesta inesperada de Liga Farmacia")
        if product.get("kinf2") != ref.external_id:
            raise FetchError(f"el catálogo devolvió otro producto ({product.get('kinf2')!r})")

        regular = _amount(product.get("precio"), "precio")
        discounted = product.get("precio_con_dscto")
        price = regular if discounted in (None, "") else _amount(discounted, "precio_con_dscto")
        online = product.get("comercio_elec")
        stock = product.get("stock")
        # Sin estos campos no se sabe el stock: leerlo como agotado dispararía OUT_OF_STOCK.
        if not isinstance(online, bool):
            raise FetchError("falta comercio_elec en el producto de Liga Farmacia")
        if isinstance(stock, bool) or not isinstance(stock, int):
            raise FetchError("falta stock en el producto de Liga Farmacia")
        name = product.get("nombre_medicamento")
        if not isinstance(name, str) or not name.strip():
            raise FetchError("falta el nombre en el producto de Liga Farmacia")
        content = product.get("contenido")
        title = (
            f"{name.strip()} ({content.strip()})"
            if isinstance(content, str) and content.strip()
            else name.strip()
        )
        return ScrapeResult(
            title=_title_case(title),
            price=price,
            list_price=regular if regular > price else None,
            currency="CLP",
            available=online and stock > 0,
            image_url=_image_url(body.get("imagen")),
        )


async def _catalog() -> tuple[dict[str, dict], dict[str, str]]:
    """Productos y fotos por kinf2, desde la caché si es reciente."""
    global _cache
    async with _cache_lock:
        if _cache is None or time.monotonic() - _cache[0] > CACHE_TTL:
            products = _products(await get_text(CATALOG_URL))
            images = _images(await get_text(IMAGES_URL))
            _cache = (time.monotonic(), products, images)
        return _cache[1], _cache[2]


def _document_array(raw: str, field: str, what: str) -> list:
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise FetchError(f"Firestore no devolvió JSON ({what})") from exc
    try:
        values = doc["fields"][field]["arrayValue"]["values"]
    except (KeyError, TypeError) as exc:
        raise FetchError(f"falta fields.{field} en el documento de {what}") from exc
    if not isinstance(values, list) or not values:
        raise FetchError(f"fields.{field} vacío en el documento de {what}")
    return values


def _products(raw: str) -> dict[str, dict]:
    products = {}
    for value in _document_array(raw, "sku", "productos"):
        item = _plain(value)
        if isinstance(item, dict) and isinstance(item.get("kinf2"), str):
            products[item["kinf2"]] = item
    if not products:
        raise FetchError("el catálogo de Liga Farmacia no trae productos")
    return products


def _images(raw: str) -> dict[str, str]:
    images = {}
    for value in _document_array(raw, "images_med", "fotos"):
        item = _plain(value)
        if not isinstance(item, dict):
            continue
        kinf2, paths = item.get("kinf2"), item.get("image")
        first = paths[0] if isinstance(paths, list) and paths else None
        if isinstance(kinf2, str) and isinstance(first, str) and kinf2 not in images:
            images[kinf2] = first
    return images


def _plain(value):
    """Valor tipado de la API REST de Firestore → valor de Python."""
    if not isinstance(value, dict) or len(value) != 1:
        return None
    kind, inner = next(iter(value.items()))
    if kind == "mapValue":
        fields = (inner or {}).get("fields") or {}
        return {k: _plain(v) for k, v in fields.items()}
    if kind == "arrayValue":
        return [_plain(v) for v in (inner or {}).get("values") or []]
    if kind == "integerValue":
        try:
            return int(inner)
        except (TypeError, ValueError):
            return None
    if kind == "nullValue":
        return None
    # stringValue, booleanValue, doubleValue, timestampValue…: tal cual.
    return inner


def _amount(value, field: str) -> int:
    """Monto en CLP. Nunca se inventa: un valor no entero o ≤ 0 es un error de lectura."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FetchError(f"{field} inválido en Liga Farmacia: {value!r}")
    return value


_WORD_RE = re.compile(r"([^\s()]+)(\s|\(|\)|$)")


def _title_case(text: str) -> str:
    """Como la ficha: minúsculas y la primera letra de cada palabra en mayúscula."""
    return _WORD_RE.sub(lambda m: m[1][:1].upper() + m[1][1:] + m[2], text.lower())


def _image_url(path) -> str | None:
    if not isinstance(path, str) or not path:
        return None
    if path.startswith("https://"):
        return path  # algunas fotos están en Firebase Storage con URL completa
    if not path.startswith("/"):
        return None
    # Como la ficha: las rutas .jpg del documento no existen; la foto real es .webp.
    return SITE_URL + path.replace(".jpg", ".webp")
