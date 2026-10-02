"""Clientes HTTP: directo con httpx, con curl_cffi (fingerprint TLS de Chrome) y a
través de FlareSolverr."""

import contextlib
import logging

import httpx
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException

from tracker.config import settings
from tracker.processors.base import FetchError, NotFoundError

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)


async def get_text(url: str, *, params: dict | None = None, timeout: float = 30) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-CL,es;q=0.9"}
    try:
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=timeout
        ) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise FetchError(f"error de red: {exc!r}") from exc
    if resp.status_code == 404:
        raise NotFoundError(f"404 en {url}")
    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} en {url}")
    return resp.text


async def get_text_impersonate(url: str, *, params: dict | None = None, timeout: float = 30) -> str:
    """Como `get_text`, pero con curl_cffi imitando a Chrome.

    Para tiendas cuyo Cloudflare bloquea el fingerprint TLS de httpx (403) y deja
    pasar a un navegador o a curl desde la misma IP (Ripley).
    """
    headers = {"Accept-Language": "es-CL,es;q=0.9"}  # el User-Agent lo pone impersonate
    try:
        async with AsyncSession(impersonate="chrome", headers=headers) as session:
            resp = await session.get(url, params=params, timeout=timeout, allow_redirects=True)
    except RequestException as exc:
        raise FetchError(f"error de red: {exc!r}") from exc
    if resp.status_code == 404:
        raise NotFoundError(f"404 en {url}")
    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} en {url}")
    return resp.text


class SolverError(FetchError):
    """Falló FlareSolverr (no el sitio): timeout del challenge, sesión rota, etc."""


# Transporte HTTP inyectable para tests (None = red real).
_transport: httpx.AsyncBaseTransport | None = None


async def _solver(cmd: dict, timeout_ms: int) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=timeout_ms / 1000 + 30, transport=_transport
        ) as client:
            resp = await client.post(settings.flaresolverr_url, json=cmd)
    except httpx.HTTPError as exc:
        raise SolverError(f"FlareSolverr no responde: {exc!r}") from exc
    try:
        data = resp.json()
    except ValueError as exc:
        raise SolverError(
            f"FlareSolverr devolvió algo que no es JSON (HTTP {resp.status_code})"
        ) from exc
    if data.get("status") != "ok":
        raise SolverError(f"FlareSolverr: {data.get('message', 'error desconocido')}")
    return data


async def flaresolverr_get(url: str, *, timeout_ms: int = 60000) -> str:
    """Pide `url` a FlareSolverr (resuelve el challenge de Cloudflare).

    Usa una sesión persistente: el navegador de FlareSolverr guarda la cookie de
    Cloudflare y las peticiones siguientes no vuelven a resolver el challenge
    (~2 s en vez de ~20 s). Si FlareSolverr falla, se descarta la sesión y se
    reintenta una vez con una nueva.
    """
    session = settings.flaresolverr_session
    try:
        return await _flaresolverr_get_once(url, session, timeout_ms)
    except SolverError as exc:
        log.warning("FlareSolverr falló (%s); reintento con sesión nueva", exc)
        with contextlib.suppress(SolverError):  # la sesión puede ya no existir
            await _solver({"cmd": "sessions.destroy", "session": session}, 10000)
        return await _flaresolverr_get_once(url, session, timeout_ms)


async def _flaresolverr_get_once(url: str, session: str, timeout_ms: int) -> str:
    # Idempotente: si ya existe responde "Session already exists."
    await _solver({"cmd": "sessions.create", "session": session}, 30000)
    data = await _solver(
        {"cmd": "request.get", "url": url, "session": session, "maxTimeout": timeout_ms},
        timeout_ms,
    )
    solution = data.get("solution") or {}
    status = solution.get("status")
    if status == 404:
        raise NotFoundError(f"404 en {url}")
    if not isinstance(status, int) or status >= 400:
        raise FetchError(f"HTTP {status} en {url} (vía FlareSolverr)")
    return solution.get("response") or ""
