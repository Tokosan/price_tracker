"""Procesador de Farmacias Ahumada (farmaciasahumada.cl, Salesforce Commerce Cloud).

El stock es por zona de despacho (`inventario_<comuna>`) y se lee con la comuna
**Santiago** fija. Cada lectura hace dos peticiones:

1. La ficha HTML (`/<slug>-<pid>.html`), con la sesión de la zona, solo para el stock.
   `Product-Variation` dice `available: true` / "In Stock" incluso en lo que la ficha
   muestra "Producto sin stock"; la ficha lo trae en el botón de compra
   (`<button class="add-to-cart" data-pid=… data-is-unavailable="true|false">`, un include
   sin caché que depende de la zona). Un pid inexistente da 404; un slug viejo redirige
   (301) al nuevo.
2. `Product-Variation?pid=<pid>` (JSON, ~20 KB) para precio, título e imagen:
   `price.sales.value` es el precio para todo medio de pago y `price.list.value` el
   normal tachado (`null` sin descuento). `hasFamiliaAhumadaPrice` (club) se ignora.

La zona se guarda en la sesión de SFCC (cookies `dwsid`/`sid`): `GET /` abre la sesión y
`POST Stores-SaveZone` (`state`, `city`) la asigna y responde la zona guardada
(`option.sectorList.inventoryZone`). Sin zona, la tienda usa Las Condes. La sesión vive
en memoria, bajo un lock. La cabecera de la ficha muestra la comuna de la sesión
(`<span class="commune">`): si no es Santiago (sesión vencida), se crea otra y se
reintenta una vez; si sigue sin serlo es un error de lectura, nunca un agotado. Como la
sesión vence a los ~30 min sin uso, tras 20 min sin usarla se renueva por adelantado.

De la ficha solo se guarda lo que se usa (controlador, comuna y botón), junto al JSON,
para que las fixtures no pesen 600 KB. No hay variantes: cada talla o presentación es su
propio producto, con su propio pid.
"""

import asyncio
import html as htmllib
import json
import re
import time

import httpx

from tracker.processors.base import FetchError, NotFoundError, ProductRef, ScrapeResult
from tracker.processors.http import USER_AGENT
from tracker.processors.sfcc import SFCCProcessor
from tracker.processors.util import to_minor

STATE = "Región Metropolitana"
CITY = "Santiago"
INVENTORY_ZONE = "inventario_santiago"
# La sesión de SFCC vence a los ~30 min sin uso y cada producto se lee cada 6 h: pasado
# este tiempo sin usarla se abre otra antes de pedir la ficha, en vez de gastar una
# petición en una ficha sin zona.
SESSION_MAX_IDLE = 20 * 60  # segundos

_PAGE_RE = re.compile(r"<div\s[^>]*\bclass=\"(?:[^\"]*\s)?page(?:\s[^\"]*)?\"[^>]*>")
_ACTION_RE = re.compile(r"\bdata-action=\"([^\"]*)\"")
_COMMUNE_RE = re.compile(r"<span\s+class=\"commune\">\s*([^<]*?)\s*</span>")
_UNAVAILABLE_RE = re.compile(r"\bdata-is-unavailable=\"(true|false)\"")


def pdp_summary(html: str, pid: str) -> dict:
    """De la ficha: el controlador de la página, la comuna de la sesión y el botón de
    compra del producto."""
    page = _PAGE_RE.search(html)
    action = _ACTION_RE.search(page.group(0)) if page else None
    commune = _COMMUNE_RE.search(html)
    button = re.search(
        rf"<button\s+class=\"add-to-cart(?:\s[^\"]*)?\"[^>]*\bdata-pid=\"{re.escape(pid)}\"[^>]*>",
        html,
    )
    return {
        "action": action.group(1) if action else None,
        "commune": htmllib.unescape(commune.group(1)) if commune else None,
        "add_to_cart": button.group(0) if button else None,
    }


class AhumadaProcessor(SFCCProcessor):
    name = "ahumada"
    label = "Farmacias Ahumada"
    hosts = frozenset({"www.farmaciasahumada.cl", "farmaciasahumada.cl"})
    canonical_host = "www.farmaciasahumada.cl"
    site_id = "ahumada-cl"
    # Los pid vistos van de 1 a 8 dígitos (`…-x-20-comprimidos-6.html`, `…-32006004.html`).
    path_re = re.compile(r"^/(?P<slug>[^/]+?)-(?P<pid>\d{1,8})\.html$", re.I)
    fixture_ext = "json"
    home_url = "https://www.farmaciasahumada.cl/"
    example_url = (
        "https://www.farmaciasahumada.cl/"
        "protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html"
    )
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio para todo medio de pago; el precio Familia Ahumada (club) no se guarda. "
        "Stock de la venta online en la comuna de Santiago: en otra comuna puede ser distinto."
    )
    # Solo para tests: un transporte falso de httpx.
    transport: httpx.AsyncBaseTransport | None = None
    # Reloj de la sesión (los tests lo reemplazan).
    clock = staticmethod(time.monotonic)

    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()
        self._cookies: httpx.Cookies | None = None
        self._used_at = 0.0  # última vez que la tienda respondió con esta sesión

    def _client(self, cookies: httpx.Cookies | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-CL,es;q=0.9"},
            cookies=cookies,
            follow_redirects=True,
            timeout=30,
            transport=self.transport,
        )

    async def _new_session(self) -> httpx.Cookies:
        """Abre una sesión y le asigna la comuna Santiago."""
        async with self._client() as client:
            await _request(client, "GET", f"https://{self.canonical_host}/")
            body = await _request(
                client,
                "POST",
                self.controller_url("Stores-SaveZone"),
                data={"state": STATE, "city": CITY},
            )
            try:
                saved = json.loads(body)
                zone = saved["option"]["sectorList"]["inventoryZone"]
            except (ValueError, KeyError, TypeError) as exc:
                raise FetchError("Ahumada no confirmó la zona de despacho") from exc
            if saved.get("success") is not True or zone != INVENTORY_ZONE:
                raise FetchError(f"Ahumada guardó la zona {zone!r}, no {INVENTORY_ZONE!r}")
            return httpx.Cookies(client.cookies)

    async def _pdp(self, ref: ProductRef) -> dict:
        """Resumen de la ficha leída con la comuna Santiago (reintenta una vez)."""
        async with self._lock:
            if self._cookies is not None and self.clock() - self._used_at > SESSION_MAX_IDLE:
                self._cookies = None  # probablemente vencida: se renueva por adelantado
            for _ in range(2):
                if self._cookies is None:
                    self._cookies = await self._new_session()
                    self._used_at = self.clock()
                async with self._client(self._cookies) as client:
                    html = await _request(client, "GET", ref.canonical_url)  # 404 → NotFound
                    self._cookies = httpx.Cookies(client.cookies)
                    self._used_at = self.clock()
                pdp = pdp_summary(html, ref.external_id)
                if pdp["action"] != "Product-Show":
                    # Página de contenido con forma de ficha: Product-Variation daría 500.
                    raise NotFoundError(f"{ref.canonical_url} no es una ficha de producto")
                if pdp["commune"] == CITY:
                    return pdp
                self._cookies = None  # la sesión perdió la zona: se crea otra
            raise FetchError(
                f"la ficha de Ahumada muestra la comuna {pdp['commune']!r}, no {CITY!r}"
            )

    async def fetch_raw(self, ref: ProductRef) -> str:
        pdp = await self._pdp(ref)
        async with self._client() as client:
            variation = await _request(
                client,
                "GET",
                self.controller_url("Product-Variation"),
                params={"pid": ref.external_id, "quantity": "1"},
            )
        # Texto crudo del JSON, sin re-serializar (como Paris).
        return f'{{"pdp": {json.dumps(pdp, ensure_ascii=False)}, "variation": {variation}}}'

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        pdp, product = _load(raw)
        if pdp.get("action") != "Product-Show":
            raise NotFoundError(f"{ref.canonical_url} no es una ficha de producto")
        if pdp.get("commune") != CITY:
            raise FetchError(f"stock de la comuna {pdp.get('commune')!r}, no de {CITY!r}")
        if str(product.get("id")) != ref.external_id:
            raise FetchError(f"Ahumada respondió el producto {product.get('id')!r}")
        unavailable = _UNAVAILABLE_RE.search(pdp.get("add_to_cart") or "")
        if not unavailable:
            raise FetchError("la ficha de Ahumada no trae el botón de compra del producto")
        prices = product.get("price") or {}
        sales = prices.get("sales") or {}
        currency = sales.get("currency") or "CLP"
        price = to_minor(sales.get("value"), currency) or None  # 0 = sin precio
        normal = to_minor((prices.get("list") or {}).get("value"), currency)
        large = (product.get("images") or {}).get("large") or []
        return ScrapeResult(
            title=(product.get("productName") or "").strip(),
            price=price,
            list_price=normal if normal and price is not None and normal > price else None,
            currency=currency,
            available=product.get("available") is True and unavailable.group(1) == "false",
            image_url=(large[0].get("url") if large and isinstance(large[0], dict) else None),
        )


async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> str:
    try:
        resp = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise FetchError(f"error de red: {exc!r}") from exc
    if resp.status_code == 404:
        raise NotFoundError(f"404 en {url}")
    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} en {url}")
    return resp.text


def _load(raw: str) -> tuple[dict, dict]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("Ahumada no devolvió JSON") from exc
    pdp = data.get("pdp") if isinstance(data, dict) else None
    variation = data.get("variation") if isinstance(data, dict) else None
    product = variation.get("product") if isinstance(variation, dict) else None
    if not isinstance(pdp, dict) or not isinstance(product, dict) or not product.get("id"):
        raise FetchError("la respuesta de Ahumada no trae el producto")
    return pdp, product
