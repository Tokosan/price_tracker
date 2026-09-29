"""Cliente de FlareSolverr con transporte HTTP simulado (sin red)."""

import json

import httpx
import pytest

from tracker.processors import http
from tracker.processors.base import FetchError, NotFoundError

URL = "https://www.entrejuegos.cl/avanzados/18597-frosthaven.html"


def ok(solution=None, message=""):
    return {"status": "ok", "message": message, "solution": solution}


def page(status=200, body="<html>ok</html>"):
    return ok({"status": status, "response": body})


TIMEOUT = {
    "status": "error",
    "message": "Error: Error solving the challenge. Timeout after 60.0 seconds.",
}


@pytest.fixture
def solver(monkeypatch):
    """Responde según una cola de respuestas para `request.get`; registra cada comando."""
    calls, gets = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        cmd = json.loads(request.content)
        calls.append(cmd)
        if cmd["cmd"] == "request.get":
            return httpx.Response(200, json=gets.pop(0))
        return httpx.Response(200, json=ok())

    monkeypatch.setattr(http, "_transport", httpx.MockTransport(handler))
    return calls, gets


async def test_usa_la_sesion_persistente(solver):
    calls, gets = solver
    gets.append(page())
    assert await http.flaresolverr_get(URL) == "<html>ok</html>"
    assert [c["cmd"] for c in calls] == ["sessions.create", "request.get"]
    assert calls[1]["session"] == calls[0]["session"] == "price_tracker"


async def test_reintenta_una_vez_con_sesion_nueva_si_falla_el_solver(solver):
    calls, gets = solver
    gets.extend([TIMEOUT, page()])
    assert await http.flaresolverr_get(URL) == "<html>ok</html>"
    assert [c["cmd"] for c in calls] == [
        "sessions.create",
        "request.get",
        "sessions.destroy",
        "sessions.create",
        "request.get",
    ]


async def test_si_falla_dos_veces_es_fetch_error(solver):
    _, gets = solver
    gets.extend([TIMEOUT, TIMEOUT])
    with pytest.raises(FetchError, match="Timeout"):
        await http.flaresolverr_get(URL)


async def test_un_error_del_sitio_no_se_reintenta(solver):
    calls, gets = solver
    gets.append(page(status=404))
    with pytest.raises(NotFoundError):
        await http.flaresolverr_get(URL)
    assert [c["cmd"] for c in calls].count("request.get") == 1
