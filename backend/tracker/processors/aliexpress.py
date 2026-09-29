"""Procesador de AliExpress, vía API oficial de afiliados (AliExpress Portals).

La página de producto se arma en el navegador y el precio llega de una API interna
protegida por un captcha (baxia) que bloquea tanto httpx como un Chrome headless. Por
eso se usa `aliexpress.affiliate.productdetail.get`, que pide una app de afiliado
(app key + secret en el .env).

Limitaciones de esa API:
- No informa stock: un producto que deja de aparecer (agotado, retirado o fuera del
  programa de afiliados) se trata como `NotFoundError` y cuenta para el backoff.
- Solo convierte a ciertas monedas (USD, EUR, MXN, BRL…); CLP no está documentada,
  así que por defecto se sigue el precio en USD (`ALIEXPRESS_CURRENCY`).
"""

import hashlib
import json
import re
import time
from datetime import timedelta
from urllib.parse import unquote, urlsplit

import httpx

from tracker.config import settings
from tracker.processors.base import FetchError, NotFoundError, Processor, ProductRef, ScrapeResult
from tracker.processors.http import USER_AGENT
from tracker.processors.util import to_minor

API_URL = "https://api-sg.aliexpress.com/sync"
METHOD = "aliexpress.affiliate.productdetail.get"
_RESPONSE_KEY = "aliexpress_affiliate_productdetail_get_response"

_HOSTS = ("aliexpress.com", "aliexpress.us")
# Links cortos que copia la app ("Compartir" → a.aliexpress.com/_xxxx).
_SHORT_HOSTS = {"a.aliexpress.com", "s.click.aliexpress.com"}
_ITEM_RE = re.compile(r"/(?:item|i)/(\d{6,20})\.html", re.I)
_MAX_REDIRECTS = 6

# Transporte HTTP inyectable para tests (None = red real).
_transport: httpx.AsyncBaseTransport | None = None


def configured() -> bool:
    return bool(settings.aliexpress_app_key and settings.aliexpress_app_secret)


def sign(secret: str, params: dict[str, str]) -> str:
    """Firma "md5" de la plataforma: MD5(secret + k1v1k2v2… ordenado + secret) en mayúsculas."""
    body = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hashlib.md5(f"{secret}{body}{secret}".encode()).hexdigest().upper()


def _is_aliexpress(host: str | None) -> bool:
    return bool(host) and any(host == d or host.endswith("." + d) for d in _HOSTS)


def _item_id(url: str) -> str | None:
    """Busca /item/<id>.html en la URL, también dentro de parámetros codificados."""
    text = url
    for _ in range(3):  # los redirects de "compartir" anidan la URL codificada
        m = _ITEM_RE.search(text)
        if m:
            return m.group(1)
        text = unquote(text)
    return None


class AliExpressProcessor(Processor):
    name = "aliexpress"
    label = "AliExpress"
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # Precios de la API: una caída grande es real, no un parseo roto.
    anomaly_drop_pct = None
    home_url = "https://www.aliexpress.com/"
    example_url = "https://www.aliexpress.com/item/1005006153442431.html"
    platform = "API de afiliados de AliExpress"
    notes = (
        "Sirve el link del navegador (/item/….html) o el de «Compartir» de la app. La API "
        "no informa stock y solo ve productos del programa de afiliados. Requiere que el "
        "admin configure una app de AliExpress Portals."
    )

    def matches(self, url: str) -> bool:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return False
        if parts.hostname in _SHORT_HOSTS:
            return len(parts.path) > 1
        return _is_aliexpress(parts.hostname) and bool(_ITEM_RE.search(parts.path))

    def normalize(self, url: str) -> ProductRef:
        parts = urlsplit(url.strip())
        m = _ITEM_RE.search(parts.path) if _is_aliexpress(parts.hostname) else None
        if not m or parts.hostname in _SHORT_HOSTS:
            raise ValueError("pega el link de un producto de AliExpress (/item/….html)")
        item = m.group(1)
        return ProductRef(item, f"https://www.aliexpress.com/item/{item}.html")

    async def expand(self, url: str) -> str:
        """Sigue un link corto hasta la URL del producto sin pedir la página final."""
        if urlsplit(url.strip()).hostname not in _SHORT_HOSTS:
            return url
        current = url.strip()
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=20, transport=_transport
        ) as client:
            for _ in range(_MAX_REDIRECTS):
                item = _item_id(current) if urlsplit(current).hostname not in _SHORT_HOSTS else None
                if item:
                    return f"https://www.aliexpress.com/item/{item}.html"
                try:
                    resp = await client.get(current)
                except httpx.HTTPError as exc:
                    raise FetchError(f"no se pudo abrir el link corto: {exc!r}") from exc
                location = resp.headers.get("location")
                if not resp.is_redirect or not location:
                    break
                current = str(resp.url.join(location))
                # Solo se siguen saltos dentro de AliExpress (no pedir URLs arbitrarias).
                if not _is_aliexpress(urlsplit(current).hostname):
                    break
        item = _item_id(current)
        if not item:
            raise NotFoundError("el link corto de AliExpress no lleva a un producto")
        return f"https://www.aliexpress.com/item/{item}.html"

    def domain(self) -> str:
        return "api-sg.aliexpress.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        if not configured():
            raise FetchError(
                "AliExpress no está configurado (faltan ALIEXPRESS_APP_KEY y "
                "ALIEXPRESS_APP_SECRET en el .env)"
            )
        params = {
            "app_key": settings.aliexpress_app_key,
            "method": METHOD,
            "sign_method": "md5",
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            "v": "2.0",
            "product_ids": ref.external_id,
            "target_currency": settings.aliexpress_currency,
            "target_language": "ES",
            "country": "CL",
        }
        if settings.aliexpress_tracking_id:
            params["tracking_id"] = settings.aliexpress_tracking_id
        params["sign"] = sign(settings.aliexpress_app_secret, params)
        try:
            async with httpx.AsyncClient(timeout=30, transport=_transport) as client:
                resp = await client.post(API_URL, data=params)
        except httpx.HTTPError as exc:
            raise FetchError(f"error de red: {exc!r}") from exc
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code} en la API de AliExpress")
        return resp.text

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise FetchError("la API de AliExpress no devolvió JSON") from exc
        if "error_response" in body:
            err = body["error_response"]
            raise FetchError(
                f"API de AliExpress: {err.get('code')} {err.get('msg') or ''} "
                f"{err.get('sub_msg') or ''}".strip()
            )
        resp = (body.get(_RESPONSE_KEY) or {}).get("resp_result") or {}
        products = ((resp.get("result") or {}).get("products") or {}).get("product") or []
        product = next((p for p in products if str(p.get("product_id")) == ref.external_id), None)
        if resp.get("resp_code") != 200 or product is None:
            raise NotFoundError(
                "AliExpress no devolvió este producto (agotado, retirado o fuera del "
                f"programa de afiliados): {resp.get('resp_msg') or 'sin resultados'}"
            )
        currency = product.get("target_sale_price_currency") or settings.aliexpress_currency
        price = to_minor(product.get("target_sale_price"), currency)
        original = to_minor(product.get("target_original_price"), currency)
        return ScrapeResult(
            title=product.get("product_title") or "",
            price=price,
            list_price=original if price is not None and original and original > price else None,
            currency=currency,
            available=price is not None,
            image_url=product.get("product_main_image_url"),
        )
