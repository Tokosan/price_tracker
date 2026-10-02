import asyncio
import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors import shopify as shopify_mod
from tracker.processors.piedrabruja import PiedraBrujaProcessor
from tracker.rules import Reading, check_anomaly

pb = PiedraBrujaProcessor()
BASE = "https://piedrabruja.cl/products"
CURSO_HANDLE = "pintado-avanzado-modulo-3"
CURSO = f"{BASE}/{CURSO_HANDLE}"
MINIS = f"{BASE}/miniaturas-para-la-bomba-de-piedrabruja"
RENEGADO = f"{BASE}/renegado-novela"


def parse(fixture, url):
    return pb.parse(fixture_text("piedrabruja", fixture), pb.normalize(url))


def variants(fixture, url):
    return pb.parse_variants(fixture_text("piedrabruja", fixture), pb.normalize(url))


def test_en_stock_sin_descuento():
    # compare_at_price igual al precio: no hay precio "antes".
    r = parse("en_stock.json", RENEGADO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Renegado (novela)",
        14990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://cdn.shopify.com/")


def test_descuento_montos_en_centavos():
    # El JSON trae price 2179000 y compare_at_price 6200000: centavos también en CLP.
    r = parse("descuento.json", MINIS)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Miniaturas para la Bomba de PiedraBruja",
        21790,
        62000,
        True,
    )


def test_agotado():
    r = parse("agotado.json", f"{BASE}/pictionary")
    assert (r.title, r.price, r.list_price, r.available) == ("Pictionary", 19990, None, False)


def test_preventa_se_puede_comprar():
    r = parse("preventa.json", f"{BASE}/unmatched-robin-hood-vs-bigfoot-esp")
    assert (r.price, r.list_price, r.available) == (29990, None, True)


def test_torneo_gratis_con_cupo_es_anomalia():
    r = parse("torneo_precio_0.json", f"{BASE}/torneo-yu-gi-oh")
    assert (r.price, r.available) == (None, True)
    reading = Reading(price=None, list_price=None, available=True)
    assert check_anomaly(reading, 5000, pb.anomaly_drop_pct, pb.sold_out_without_price)


def test_sin_variant_sigue_la_primera_fecha():
    r = parse("curso_fechas.json", CURSO)
    assert r.title == "Curso de Pintado Avanzado Presencial - Módulo 3 (26/10/2026)"
    assert (r.price, r.list_price, r.available) == (30000, None, True)


def test_variant_elige_la_fecha():
    r = parse("curso_fechas.json", f"{CURSO}?variant=52433109352728")
    assert r.title.endswith("(28/12/2026)")


def test_variante_que_ya_no_existe():
    with pytest.raises(NotFoundError):
        parse("curso_fechas.json", f"{CURSO}?variant=123")


def test_selector_de_fechas():
    vs = variants("curso_fechas.json", CURSO)
    assert [v.label for v in vs] == [
        "26/10/2026: $30.000",
        "30/11/2026: $30.000",
        "28/12/2026: $30.000",
    ]
    # Sin variant en el link, la actual también se devuelve con el suyo: queda fija.
    assert vs[0].selected and vs[0].url == f"{CURSO}?variant=52433109287192"
    assert [v.selected for v in vs[1:]] == [False, False]
    for v in vs:
        assert v.external_id == CURSO_HANDLE
        assert pb.normalize(v.url) == ProductRef(CURSO_HANDLE, v.url, v.variant_id)


def test_selector_con_variant_y_agotadas():
    url = f"{BASE}/pintado-avanzado-modulo-2?variant=52433106043160"
    vs = variants("curso_fechas_agotado.json", url)
    assert vs[0].selected and vs[0].url == url
    assert vs[0].label == "31/08/2026: $30.000 (agotada)"
    assert all(v.label.endswith("(agotada)") for v in vs)


@pytest.mark.parametrize("url", [RENEGADO, f"{RENEGADO}?variant=51849086304536"])
def test_producto_simple_se_ofrece_sin_variant(url):
    vs = variants("en_stock.json", url)
    assert [(v.url, v.external_id, v.variant_id, v.selected) for v in vs] == [
        (RENEGADO, "renegado-novela", "", True)
    ]


def test_respuesta_que_no_es_json_es_error_de_lectura():
    with pytest.raises(FetchError):
        pb.parse("<html>Just a moment...</html>", pb.normalize(RENEGADO))
    data = json.loads(fixture_text("piedrabruja", "en_stock.json"))
    del data["variants"][0]["available"]
    with pytest.raises(FetchError):
        pb.parse(json.dumps(data), pb.normalize(RENEGADO))


def test_fetch_pide_el_json_de_la_ficha(monkeypatch):
    urls = []

    async def fake_get_text(url, **kwargs):
        urls.append(url)
        return "{}"

    monkeypatch.setattr(shopify_mod, "get_text", fake_get_text)
    ref = pb.normalize(f"https://www.piedrabruja.cl/collections/juegos/products/{CURSO_HANDLE}")
    asyncio.run(pb.fetch_raw(ref))
    assert urls == [f"https://piedrabruja.cl/products/{CURSO_HANDLE}.js"]


@pytest.mark.parametrize(
    ("url", "variant"),
    [
        (CURSO, ""),
        (f"https://www.piedrabruja.cl/products/{CURSO_HANDLE}", ""),
        (f"http://piedrabruja.cl/products/{CURSO_HANDLE}/", ""),
        (f"https://PIEDRABRUJA.CL/products/{CURSO_HANDLE.upper()}?utm_source=x#top", ""),
        (f"https://piedrabruja.cl/collections/talleres/products/{CURSO_HANDLE}", ""),
        (f"{CURSO}?variant=52433109319960", "52433109319960"),
        (
            f"https://piedrabruja.cl/collections/x/products/{CURSO_HANDLE}?variant=52433109319960",
            "52433109319960",
        ),
        (f"{CURSO}?variant=abc", ""),
    ],
)
def test_normaliza_url(url, variant):
    ref = pb.normalize(url)
    assert ref.external_id == CURSO_HANDLE
    assert ref.variant_id == variant
    assert ref.canonical_url == CURSO + (f"?variant={variant}" if variant else "")


def test_matchea_solo_fichas_de_su_dominio():
    assert pb.domain() == "piedrabruja.cl"
    assert find_processor(CURSO).name == "piedrabruja"
    assert not pb.matches("https://piedrabruja.cl/")
    assert not pb.matches("https://piedrabruja.cl/collections/juegos-de-mesa")
    assert not pb.matches("https://piedrabruja.cl/collections/all/products")
    assert not pb.matches("https://piedrabruja.cl/search?q=pokemon")
    assert not pb.matches("https://piedrabruja.cl/pages/contacto")
    assert not pb.matches("https://piedrabruja.cl/products/pictionary/otra-cosa")
    assert not pb.matches("https://piedrabruja.cl.evil.com/products/pictionary")
    assert not pb.matches("https://evilpiedrabruja.cl/products/pictionary")
    assert not pb.matches("ftp://piedrabruja.cl/products/pictionary")
