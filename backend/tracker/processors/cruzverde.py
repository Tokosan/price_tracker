"""Procesador de Cruz Verde (cruzverde.cl).

La web es una SPA de Angular (el HTML llega vacío), así que se lee la API que usa el
propio front, `api.cruzverde.cl`. Esa API exige una sesión: `POST
/customer-service/login` con `{}` abre una de invitado y la devuelve en la cookie
`connect.sid` (basta esa cookie; las de Incapsula no hacen falta). La respuesta del login
trae además un token de Salesforce que no se usa ni se guarda.

La sesión vive en memoria del proceso y se comparte entre lecturas. Si la API responde
401 `INVALID_SESSION` (sesión vencida), se hace login otra vez y se reintenta una sola
vez. El login va bajo un lock para que varias lecturas que encuentran la sesión vencida a
la vez no abran una cada una.

Precio: `productData.prices` = `{"price-sale-cl": …, "price-list-cl": …}` (enteros en
CLP). Se usa el rebajado (`price-sale-cl`) si existe y, si no, el normal; el normal es el
precio "antes" solo si es mayor. Los precios de convenios, Club o "necesidad de salud"
(`healthNeedsPrice`, `promotions`) no se guardan. Stock: `stock` (sin zona; con
`?inventoryId=` cambia la cantidad pero no el precio). Un agotado tiene `stock: 0` y
conserva sus precios.

Un id que no existe responde HTTP 500 `INTERNAL_ERROR`, igual que una falla del servidor;
el buscador tampoco sirve para distinguirlo (no lista los productos agotados), así que se
trata como `FetchError`.
"""

import asyncio
import json
import logging
import re
from datetime import timedelta

import httpx

from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import USER_AGENT

log = logging.getLogger(__name__)

# /<slug>/<id>.html. Sin slug (`/<id>.html`) la SPA muestra "Página no encontrada"; con
# cualquier slug muestra el producto, así que el slug no importa para identificarlo.
_URL_RE = re.compile(r"^https?://(?:www\.)?cruzverde\.cl/([^/?#]+)/(\d+)\.html/?(?:[?#].*)?$", re.I)
API_URL = "https://api.cruzverde.cl"
LOGIN_URL = f"{API_URL}/customer-service/login"
DETAIL_URL = f"{API_URL}/product-service/products/detail/{{id}}"
SESSION_COOKIE = "connect.sid"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
    "Origin": "https://www.cruzverde.cl",
    "Referer": "https://www.cruzverde.cl/",
}

# Transporte HTTP inyectable para tests (None = red real).
_transport: httpx.AsyncBaseTransport | None = None
# Valor de la cookie `connect.sid` de la sesión invitado vigente (None = sin sesión).
_session: str | None = None
_session_lock = asyncio.Lock()


class CruzVerdeProcessor(Processor):
    name = "cruzverde"
    label = "Cruz Verde"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    home_url = "https://www.cruzverde.cl/"
    example_url = "https://www.cruzverde.cl/xumadol-paracetamol-1000-mg-20-comprimidos/266145.html"
    platform = "API de Cruz Verde (sesión de invitado)"
    supports_variants = False
    supports_list_price = True
    notes = (
        "Precio de la compra online: el rebajado si lo hay y, si no, el normal; el normal "
        "queda como precio «antes». Los descuentos de convenios, Club o «necesidad de salud» "
        "no se guardan. Un producto agotado sigue mostrando su precio. Stock del despacho, "
        "sin elegir comuna."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de Cruz Verde")
        slug, product_id = m.group(1), m.group(2)
        return ProductRef(product_id, f"https://www.cruzverde.cl/{slug}/{product_id}.html")

    def domain(self) -> str:
        return "www.cruzverde.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        url = DETAIL_URL.format(id=ref.external_id)
        try:
            async with httpx.AsyncClient(
                headers=HEADERS, timeout=30, transport=_transport
            ) as client:
                session = _session or await _renew_session(client, stale=None)
                resp = await _get(client, url, session)
                if _invalid_session(resp):
                    log.info("sesión de Cruz Verde vencida; nuevo login")
                    session = await _renew_session(client, stale=session)
                    resp = await _get(client, url, session)
        except httpx.HTTPError as exc:
            raise FetchError(f"error de red: {exc!r}") from exc
        if _invalid_session(resp):
            raise FetchError("Cruz Verde rechazó la sesión recién creada")
        if resp.status_code == 404:
            raise NotFoundError(f"404 en {url}")
        if resp.status_code == 500:
            # Así responde también un id que no existe: no se puede distinguir.
            raise FetchError(f"HTTP 500 en {url} (el producto no existe o falló la API)")
        if resp.status_code >= 400:
            raise FetchError(f"HTTP {resp.status_code} en {url}")
        return resp.text

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("la API de Cruz Verde no devolvió JSON") from exc
        data = body.get("productData") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise FetchError("falta 'productData' en la respuesta de Cruz Verde")
        if str(data.get("id")) != ref.external_id:
            raise FetchError(f"la API devolvió otro producto ({data.get('id')!r})")

        prices = data.get("prices")
        if not isinstance(prices, dict):
            prices = {}
        sale = _amount(prices.get("price-sale-cl"))
        regular = _amount(prices.get("price-list-cl"))
        price = sale or regular
        # Sin el campo no se sabe el stock: leerlo como agotado dispararía OUT_OF_STOCK.
        stock = data.get("stock")
        if not isinstance(stock, int) or isinstance(stock, bool):
            raise FetchError("falta stock en la respuesta de Cruz Verde")
        images = data.get("images") or []
        image = images[0].get("link") if images and isinstance(images[0], dict) else None
        return ScrapeResult(
            title=(data.get("name") or "").strip(),
            price=price,
            list_price=regular if regular and price is not None and regular > price else None,
            currency="CLP",
            available=stock > 0,
            image_url=image or None,
        )


def _amount(value) -> int | None:
    """Monto en CLP (entero). Un cero o un valor que no es número es un dato roto."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    amount = int(value)
    return amount if amount > 0 else None


def _invalid_session(resp: httpx.Response) -> bool:
    return resp.status_code == 401


async def _get(client: httpx.AsyncClient, url: str, session: str) -> httpx.Response:
    # La cookie va a mano: el cliente es nuevo en cada lectura y la sesión se comparte.
    return await client.get(url, headers={"Cookie": f"{SESSION_COOKIE}={session}"})


async def _renew_session(client: httpx.AsyncClient, *, stale: str | None) -> str:
    """Abre una sesión invitado nueva, salvo que otra lectura ya la haya renovado.

    `stale` es la sesión que se sabe vencida (None si no había ninguna).
    """
    global _session
    async with _session_lock:
        # Otra lectura pudo renovarla mientras se esperaba el lock.
        if _session is not None and _session != stale:
            return _session
        resp = await client.post(LOGIN_URL, json={})
        if resp.status_code not in (200, 201):
            raise FetchError(f"login de invitado en Cruz Verde: HTTP {resp.status_code}")
        session = resp.cookies.get(SESSION_COOKIE)
        if not session:
            raise FetchError("el login de invitado de Cruz Verde no devolvió sesión")
        _session = session
        return session
