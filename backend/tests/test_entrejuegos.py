import re

import pytest

from tests.conftest import fixture_text
from tracker.processors.entrejuegos import EntrejuegosProcessor

ej = EntrejuegosProcessor()
FLIP7 = "https://www.entrejuegos.cl/juegos-de-mesa/19754-flip-7.html"


def test_flip7_en_stock():
    r = ej.parse(fixture_text("entrejuegos", "flip7_en_stock.html"), ej.normalize(FLIP7))
    assert r.title == "Flip 7"
    assert r.price == 16990
    assert r.currency == "CLP"
    assert r.available is True
    assert r.list_price is None
    assert r.image_url.endswith(".jpg")


def test_agotado():
    url = "https://www.entrejuegos.cl/juegos-de-mesa/11076-pictureka.html"
    r = ej.parse(fixture_text("entrejuegos", "pictureka_agotado.html"), ej.normalize(url))
    assert r.title == "Pictureka!"
    assert r.price == 23990
    assert r.available is False


def test_oferta_trae_precio_base():
    url = "https://www.entrejuegos.cl/accesorios/18281-marvel-heroclix-deep-cuts-unpainted-miniatures-cyclops.html"
    r = ej.parse(fixture_text("entrejuegos", "heroclix_oferta.html"), ej.normalize(url))
    assert r.price == 2990
    assert r.list_price == 4990


def test_sin_data_product_usa_json_ld():
    raw = fixture_text("entrejuegos", "pictureka_agotado.html")
    raw = re.sub(r'data-product="[^"]*"', "", raw)
    r = ej.parse(raw, ej.normalize("https://www.entrejuegos.cl/x/11076-pictureka.html"))
    assert r.price == 23990
    assert r.available is False


def test_solo_meta_tags():
    raw = (
        '<meta property="og:title" content="Juego">'
        '<meta property="product:price:amount" content="12990">'
        '<meta property="product:price:currency" content="CLP">'
        '<meta property="product:availability" content="in stock">'
    )
    r = ej.parse(raw, ej.normalize(FLIP7))
    assert (r.title, r.price, r.available) == ("Juego", 12990, True)


def test_pagina_sin_datos_da_precio_none():
    r = ej.parse("<html>Just a moment...</html>", ej.normalize(FLIP7))
    assert r.price is None


@pytest.mark.parametrize(
    "url",
    [
        FLIP7,
        "https://entrejuegos.cl/juegos-de-mesa/19754-flip-7.html?utm_source=x",
        "https://www.entrejuegos.cl/inicio/19754-flip-7.html#/1-idioma-espanol",
    ],
)
def test_normaliza_url(url):
    ref = ej.normalize(url)
    assert ref.external_id == "19754"
    assert ref.canonical_url.startswith("https://www.entrejuegos.cl/")
    assert "?" not in ref.canonical_url and "#" not in ref.canonical_url


def test_no_matchea_categorias():
    assert not ej.matches("https://www.entrejuegos.cl/1064-juegos-de-mesa")
