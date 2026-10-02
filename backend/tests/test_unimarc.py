import json

import httpx
import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor, http, unimarc
from tracker.processors.unimarc import UnimarcProcessor

um = UnimarcProcessor()
ARROZ = "https://www.unimarc.cl/product/arroz-basmati-miraflores-400-gr"


def parse(fixture, url=ARROZ):
    return um.parse(fixture_text("unimarc", fixture), um.normalize(url))


def test_en_stock():
    r = parse("arroz_en_stock.json")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Arroz Miraflores basmati premium bolsa 400 g",
        3190,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://unimarc.vtexassets.com/")


def test_descuento_trae_precio_antes():
    url = "https://www.unimarc.cl/product/choclo-congelado-nuestra-cocina-500gr"
    r = parse("choclo_descuento.json", url)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Choclo grano Nuestra Cocina 500 g",
        1230,
        1750,
        True,
    )


def test_precio_club_se_toma_y_lleva_x_se_ignora():
    # Club Unimarc: 400 (antes 2.990). `promotion.price` (897, "lleva X") no se usa.
    r = parse("volantin_club.json", "https://www.unimarc.cl/product/volantin-chile-fp26-dkora")
    assert (r.price, r.list_price, r.available) == (400, 2990, True)


def test_agotado_conserva_el_precio():
    url = "https://www.unimarc.cl/product/mantequilla-con-sal-los-peumos-250-gr"
    r = parse("mantequilla_agotado.json", url)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Mantequilla Los Peumos con sal 250 g",
        2790,
        None,
        False,
    )


def test_respaldo_html_usa_next_data():
    r = parse("arroz_html.html")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Arroz Miraflores basmati premium bolsa 400 g",
        3190,
        None,
        True,
    )
    url = "https://www.unimarc.cl/product/mantequilla-con-sal-los-peumos-250-gr"
    r = parse("mantequilla_agotado_html.html", url)
    assert (r.price, r.available) == (2790, False)


def test_respaldo_vtex():
    r = parse("arroz_vtex.json")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Arroz Miraflores basmati premium bolsa 400 g",
        3190,
        None,
        True,
    )


def test_vtex_vacio_no_es_producto_inexistente():
    with pytest.raises(FetchError) as exc:
        parse("vtex_vacio.json")
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize(
    "cambio",
    [
        lambda p: p.pop("price"),
        lambda p: p["price"].update(price=""),
        lambda p: p["price"].update(price="$0"),
        lambda p: p["price"].pop("availableQuantity"),
        lambda p: p["price"].update(availableQuantity=None),
    ],
    ids=["sin-price", "price-vacio", "price-0", "sin-cantidad", "cantidad-null"],
)
def test_bff_incompleto_es_error_de_lectura(cambio):
    data = json.loads(fixture_text("unimarc", "arroz_en_stock.json"))
    cambio(data["products"][0])
    with pytest.raises(FetchError):
        um.parse(json.dumps(data), um.normalize(ARROZ))


@pytest.mark.parametrize(
    "raw",
    ['{"products": []}', "{}", "no es json", "<html><title>Access Denied</title></html>"],
)
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError) as exc:
        um.parse(raw, um.normalize(ARROZ))
    assert not isinstance(exc.value, NotFoundError)


def _fake_get_text(monkeypatch, responses):
    """Cada respuesta es un texto o una excepción; guarda (url, kwargs) de cada llamada."""
    calls = []

    async def fake(url, **kwargs):
        calls.append((url, kwargs))
        out = responses[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(unimarc, "get_text", fake)
    return calls


async def test_fetch_lee_el_bff_con_http2_y_headers(monkeypatch):
    bff = fixture_text("unimarc", "arroz_en_stock.json")
    calls = _fake_get_text(monkeypatch, [bff])
    assert await um.fetch_raw(um.normalize(ARROZ)) == bff
    url, kwargs = calls[0]
    assert url == (
        "https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search/by-slug/"
        "arroz-basmati-miraflores-400-gr"
    )
    assert kwargs["http2"] and kwargs["browser_headers"]
    assert {"channel": "UNIMARC", "source": "web", "version": "1.0.0"}.items() <= kwargs[
        "headers"
    ].items()


async def test_fetch_inexistente_lo_decide_el_404_del_html(monkeypatch):
    calls = _fake_get_text(
        monkeypatch, [FetchError("HTTP 500"), NotFoundError("404"), "no debería llegar"]
    )
    with pytest.raises(NotFoundError):
        await um.fetch_raw(um.normalize(ARROZ))
    assert [c[0] for c in calls] == [
        "https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search/by-slug/"
        "arroz-basmati-miraflores-400-gr",
        ARROZ,
    ]
    assert calls[1][1]["http2"] and calls[1][1]["browser_headers"]


async def test_fetch_bff_sin_producto_pasa_al_html(monkeypatch):
    html = fixture_text("unimarc", "arroz_html.html")
    calls = _fake_get_text(monkeypatch, ['{"products": []}', html])
    raw = await um.fetch_raw(um.normalize(ARROZ))
    assert raw == html and len(calls) == 2
    assert um.parse(raw, um.normalize(ARROZ)).price == 3190


async def test_fetch_con_akamai_bloqueando_usa_vtex(monkeypatch):
    vtex = fixture_text("unimarc", "arroz_vtex.json")
    calls = _fake_get_text(monkeypatch, [FetchError("HTTP 403"), FetchError("HTTP 403"), vtex])
    assert await um.fetch_raw(um.normalize(ARROZ)) == vtex
    url, kwargs = calls[2]
    assert url == (
        "https://unimarc.vtexcommercestable.com.br/api/catalog_system/pub/products/search/"
        "arroz-basmati-miraflores-400-gr/p?sc=39"
    )
    assert kwargs == {}  # VTEX no tiene WAF: get_text normal


async def test_get_text_por_defecto_no_cambia(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text="ok")

    real = httpx.AsyncClient

    def client(**kwargs):
        seen.append(kwargs)
        return real(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(http.httpx, "AsyncClient", client)
    assert await http.get_text("https://example.com/") == "ok"
    kwargs, request = seen
    assert kwargs["http2"] is False
    assert "sec-fetch-mode" not in request.headers
    assert request.headers["user-agent"] == http.USER_AGENT

    seen.clear()
    await http.get_text(
        "https://example.com/", http2=True, browser_headers=True, headers={"X": "1"}
    )
    kwargs, request = seen
    assert kwargs["http2"] is True
    assert request.headers["sec-fetch-mode"] == "navigate"
    assert request.headers["x"] == "1"


@pytest.mark.parametrize(
    "url",
    [
        ARROZ,
        "https://unimarc.cl/product/arroz-basmati-miraflores-400-gr",
        "http://www.unimarc.cl/product/arroz-basmati-miraflores-400-gr/",
        "https://WWW.UNIMARC.CL/product/Arroz-Basmati-Miraflores-400-GR?utm_source=x#top",
    ],
)
def test_normaliza_url(url):
    assert um.normalize(url) == ProductRef("arroz-basmati-miraflores-400-gr", ARROZ)


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(ARROZ).name == "unimarc"
    assert not um.matches("https://www.unimarc.cl/")
    assert not um.matches("https://www.unimarc.cl/category/despensa/arroz-y-legumbres")
    assert not um.matches("https://www.unimarc.cl/search?q=arroz")
    assert not um.matches("https://www.unimarc.cl/product/")
    assert not um.matches("https://www.unimarc.cl.evil.com/product/arroz-basmati-miraflores-400-gr")
    assert not um.matches("https://evilunimarc.cl/product/arroz-basmati-miraflores-400-gr")
