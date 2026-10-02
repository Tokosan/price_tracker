import json
import re

import pytest
from curl_cffi.requests.exceptions import RequestException

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor, http
from tracker.processors.ripley import RipleyProcessor

ripley = RipleyProcessor()
ALMOHADA = "https://simple.ripley.cl/almohada-cic-da-soft-sleep-70-x-50-cm-blanco-2000385824701p"
MERRELL = "https://simple.ripley.cl/zapatilla-hombre-moab-speed-2-gris-merrell-mpm10003530190"
MINI = "https://simple.ripley.cl/minicomponente-sony-mhc-gpx555-2000347375067p"
POLERA = "https://simple.ripley.cl/polera-hombre-nike-reset-2000407145159"
PANTALON = "https://simple.ripley.cl/pantalon-de-buzo-mujer-under-armour-1382735-2000399379907"


def parse(fixture, url):
    return ripley.parse(fixture_text("ripley", fixture), ripley.normalize(url))


def variants(fixture, url):
    return ripley.parse_variants(fixture_text("ripley", fixture), ripley.normalize(url))


def test_descuento_ignora_la_tarjeta_ripley():
    raw = fixture_text("ripley", "descuento_almohada.html")
    assert '"ripley":{"value":"$13.990"' in raw
    r = ripley.parse(raw, ripley.normalize(ALMOHADA))
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "ALMOHADA CIC DA SOFT SLEEP 70 X 50 CM BLANCO",
        14990,
        17990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://home.ripley.cl/store/Attachment/")


def test_marketplace_sin_descuento():
    r = parse("marketplace_merrell_tallas.html", MERRELL)
    assert r.title == "ZAPATILLA HOMBRE MOAB SPEED 2 GRIS MERRELL"
    assert (r.price, r.list_price, r.available) == (119990, None, True)


def test_agotado():
    r = parse("agotado_minicomponente.html", MINI)
    assert (r.price, r.list_price, r.available) == (229990, None, False)


def test_talla_agotada_y_talla_con_stock():
    s = parse("tallas_stock_mixto_polera.html", POLERA + "?sku=2000407145197")
    assert s.title == "POLERA HOMBRE NIKE RESET (Blanco, S)"
    assert (s.price, s.list_price, s.available) == (23990, 29990, False)
    m = parse("tallas_stock_mixto_polera.html", POLERA + "?sku=2000407145180")
    assert m.title == "POLERA HOMBRE NIKE RESET (Blanco, M)"
    assert (m.price, m.available) == (23990, True)
    # Sin talla: lo que muestra la ficha (hay stock en alguna).
    a = parse("tallas_stock_mixto_polera.html", POLERA)
    assert (a.title, a.price, a.available) == ("POLERA HOMBRE NIKE RESET", 23990, True)


def test_precio_distinto_por_talla():
    s = parse("agotado_precio_por_talla_pantalon.html", PANTALON + "?sku=2000399379921")
    m = parse("agotado_precio_por_talla_pantalon.html", PANTALON + "?sku=2000399379914")
    assert (s.price, s.list_price, s.available) == (12990, 42990, False)
    assert (m.price, m.list_price, m.available) == (25990, 42990, False)
    # Sin talla: el más bajo (todas agotadas).
    a = parse("agotado_precio_por_talla_pantalon.html", PANTALON)
    assert (a.price, a.available) == (12990, False)


def test_talla_que_ya_no_esta_es_error_de_lectura():
    with pytest.raises(FetchError, match="ya no está"):
        parse("tallas_stock_mixto_polera.html", POLERA + "?sku=99999999")


def test_pagina_404_no_es_producto():
    with pytest.raises(NotFoundError, match="/404"):
        parse("no_existe_404.html", ALMOHADA)


@pytest.mark.parametrize(
    "raw", ["<html>sin datos</html>", '<script id="__NEXT_DATA__">{x</script>']
)
def test_pagina_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        ripley.parse(raw, ripley.normalize(ALMOHADA))


def _with_prices(fixture, **prices):
    raw = fixture_text("ripley", fixture)
    m = re.search(r'(<script id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', raw, re.S)
    data = json.loads(m.group(2))
    pps = data["props"]["pageProps"]["detailProps"]["data"]["product"]["parentpricestock"]
    for kind, value in prices.items():
        pps["price"][kind] = None if value is None else {"valueNumber": value}
    return raw[: m.start(2)] + json.dumps(data) + raw[m.end(2) :]


def test_sin_precio_sale_usa_el_normal():
    raw = _with_prices("descuento_almohada.html", sale=None)
    r = ripley.parse(raw, ripley.normalize(ALMOHADA))
    assert (r.price, r.list_price) == (17990, None)


def test_sin_precios_no_inventa_precio():
    raw = _with_prices("descuento_almohada.html", sale=0, master=0)
    r = ripley.parse(raw, ripley.normalize(ALMOHADA))
    assert (r.price, r.list_price) == (None, None)


def test_variantes_con_stock_mixto():
    vs = variants("tallas_stock_mixto_polera.html", POLERA)
    assert vs[0].selected and vs[0].variant_id == ""
    assert vs[0].label == "Cualquier talla: desde $23.990"
    assert [v.label for v in vs[1:]] == [
        "Blanco, S: $23.990 (agotada)",
        "Blanco, M: $23.990",
        "Blanco, L: $23.990",
        "Blanco, XL: $23.990",
    ]
    for v in vs:
        ref = ripley.normalize(v.url)
        assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
            v.external_id,
            v.variant_id,
            v.url,
        )


def test_variante_elegida_va_primero():
    vs = variants("tallas_stock_mixto_polera.html", POLERA + "?sku=2000407145180")
    assert vs[0].selected and vs[0].label == "Blanco, M: $23.990"
    assert sum(v.selected for v in vs) == 1


def test_sin_variantes():
    assert variants("descuento_almohada.html", ALMOHADA) == []
    assert variants("agotado_minicomponente.html", MINI) == []


@pytest.mark.parametrize(
    ("url", "external_id", "variant_id"),
    [
        (ALMOHADA, "2000385824701p", ""),
        ("https://simple.ripley.cl/2000385824701P", "2000385824701p", ""),
        (
            "http://simple.ripley.cl/Otro-Slug-2000385824701p/?s=mdco&utm_source=wa#x",
            "2000385824701p",
            "",
        ),
        (MERRELL + "?sku=28570706", "mpm10003530190", "28570706"),
        ("https://simple.ripley.cl/MPM10003530190?sku=abc", "mpm10003530190", ""),
        ("https://simple.ripley.cl/polera-hombre-nike-reset-2000407145166", "2000407145166", ""),
    ],
)
def test_normaliza_url(url, external_id, variant_id):
    ref = ripley.normalize(url)
    assert (ref.external_id, ref.variant_id) == (external_id, variant_id)
    expected = f"https://simple.ripley.cl/{external_id}"
    assert ref.canonical_url == expected + (f"?sku={variant_id}" if variant_id else "")


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(ALMOHADA).name == "ripley"
    assert find_processor(MERRELL).name == "ripley"
    assert not ripley.matches("https://simple.ripley.cl/")
    assert not ripley.matches("https://simple.ripley.cl/search/zapatillas%20hombre")
    assert not ripley.matches("https://simple.ripley.cl/tecno/computacion/notebooks")
    assert not ripley.matches("https://simple.ripley.cl/minisitios/estatico/marcas-mercado")
    assert not ripley.matches("https://simple.ripley.cl/nike/2000407145166")
    assert not ripley.matches("https://simple.ripley.cl/cyber-2024")
    assert not ripley.matches("https://simple.ripley.cl.evil.com/almohada-2000385824701p")
    assert not ripley.matches("https://evilsimple.ripley.cl/almohada-2000385824701p")
    assert not ripley.matches("https://www.ripley.com.pe/almohada-2000385824701p")
    with pytest.raises(ValueError):
        ripley.normalize("https://simple.ripley.cl/search/x")


async def test_fetch_pide_la_ficha_sin_slug_ni_sku(monkeypatch):
    calls = []

    async def fake(url, **kw):
        calls.append(url)
        return fixture_text("ripley", "tallas_stock_mixto_polera.html")

    monkeypatch.setattr("tracker.processors.ripley.get_text_impersonate", fake)
    r = await ripley.fetch(ripley.normalize(POLERA + "?sku=2000407145180"))
    assert r.available is True
    assert calls == ["https://simple.ripley.cl/2000407145159"]


class _FakeSession:
    """AsyncSession falsa para probar el manejo de errores de `get_text_impersonate`."""

    def __init__(self, result, **kw):
        self.result = result
        self.kw = kw

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (_Resp(404), NotFoundError),
        (_Resp(403), FetchError),
        (_Resp(500), FetchError),
        (RequestException("timeout"), FetchError),
    ],
)
async def test_get_text_impersonate_errores(monkeypatch, result, error):
    created = []

    def session(**kw):
        created.append(kw)
        return _FakeSession(result, **kw)

    monkeypatch.setattr(http, "AsyncSession", session)
    with pytest.raises(error):
        await http.get_text_impersonate("https://simple.ripley.cl/x")
    assert created[0]["impersonate"] == "chrome"


async def test_get_text_impersonate_ok(monkeypatch):
    monkeypatch.setattr(http, "AsyncSession", lambda **kw: _FakeSession(_Resp(200, "hola")))
    assert await http.get_text_impersonate("https://simple.ripley.cl/x") == "hola"
