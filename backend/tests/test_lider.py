import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, find_processor
from tracker.processors.lider import LiderProcessor

lider = LiderProcessor()
PILLOWS = "https://super.lider.cl/ip/cereales/00780242000793"


def parse(fixture, url=PILLOWS):
    return lider.parse(fixture_text("lider", fixture), lider.normalize(url))


def test_en_stock():
    r = parse("pillows_en_stock.html")
    assert (r.title, r.price, r.currency, r.available) == (
        "Cereales Pillows Sabor Chocolate, 350 g",
        3690,
        "CLP",
        True,
    )
    assert r.list_price is None
    assert r.image_url.startswith("https://i5.walmartimages.cl/")


def test_descuento_trae_precio_antes():
    r = parse("monoballs_descuento.html", "https://super.lider.cl/ip/cereales/00780221516889")
    assert r.title == "Cereal Mono Balls, 400 g"
    assert (r.price, r.list_price, r.available) == (2790, 3290, True)


def test_agotado():
    r = parse("granola_agotado.html", "https://super.lider.cl/ip/cereales/00780467391367")
    assert r.available is False
    assert (r.price, r.list_price) == (4550, 5390)


def test_granel_se_marca_por_kg():
    r = parse("palta_granel.html", "https://super.lider.cl/ip/frutas/00203030000000")
    assert r.title == "Palta hass granel (por kg)"
    assert (r.price, r.available) == (6290, True)


def test_captcha_es_error_de_lectura():
    with pytest.raises(FetchError, match="PerimeterX"):
        parse("bloqueado.html")


def test_sin_next_data_usa_json_ld():
    raw = fixture_text("lider", "monoballs_descuento.html").replace("__NEXT_DATA__", "x")
    r = lider.parse(raw, lider.normalize(PILLOWS))
    assert (r.title, r.price, r.available) == ("Cereal Mono Balls, 400 g", 2790, True)
    assert r.list_price is None


def test_pagina_sin_producto_da_precio_none():
    r = lider.parse("<html><title>Lider</title></html>", lider.normalize(PILLOWS))
    assert r.price is None and r.available is False


@pytest.mark.parametrize(
    "url",
    [
        PILLOWS,
        "https://super.lider.cl/ip/00780242000793",
        "https://super.lider.cl/ip/lo-que-sea/00780242000793/",
        "http://SUPER.lider.cl/ip/cereales/00780242000793?utm_source=wa#top",
    ],
)
def test_normaliza_url(url):
    ref = lider.normalize(url)
    assert ref.external_id == "00780242000793"
    assert ref.canonical_url == "https://super.lider.cl/ip/00780242000793"


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(PILLOWS).name == "lider"
    assert not lider.matches("https://super.lider.cl/")
    assert not lider.matches("https://super.lider.cl/browse/despensa/cereales/cereales-y-avenas")
    assert not lider.matches("https://super.lider.cl/search?q=cereal")
    assert not lider.matches("https://super.lider.cl/ip/cereales/pillows")
    assert not lider.matches("https://super.lider.cl.evil.com/ip/cereales/00780242000793")
    assert not lider.matches("https://evilsuper.lider.cl/ip/cereales/00780242000793")
