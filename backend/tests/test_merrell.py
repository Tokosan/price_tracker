"""Tests del procesador de Merrell (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.merrell import MerrellProcessor

proc = MerrellProcessor()
URL = "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l"


def parse(fixture, url):
    return proc.parse(fixture_text("merrell", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Camisa Hombre Franela Winter (S)",
        19995,
        39990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("merrell", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l"
        ),
    )
    assert len(variantes) == 5
    assert variantes[0].selected and variantes[0].variant_id == "59056505159761"
    assert variantes[0].label == "S: $19.995 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 4


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l?variant=59056505290833",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Camisa Hombre Franela Winter (XXL)",
        19995,
        39990,
        True,
    )


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.merrell.cl/products/zapatilla-mujer-crosslander-4-eco-verde-merrell-j00005664-h63",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatilla Mujer Crosslander 4 Eco Verde Merrell (5)",
        89990,
        None,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
        "https://merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
        "http://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l/",
        "https://www.merrell.cl/products/CAMISA-M-L-HOMBRE-M-FRANELA-WINTER-MERRELL-MEW23-MSR001-28L?utm_source=x#top",
        "https://www.merrell.cl/collections/hombre/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.merrell.cl"
    assert find_processor(URL).name == "merrell"
    assert not proc.matches("https://www.merrell.cl/")
    assert not proc.matches("https://www.merrell.cl/collections/hombre")
    assert not proc.matches("https://www.merrell.cl/search?q=polera")
    assert not proc.matches("https://www.merrell.cl/pages/tiendas")
    assert not proc.matches(
        "https://merrell.cl.evil.com/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l"
    )
    assert not proc.matches(
        "https://notmerrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l"
    )
