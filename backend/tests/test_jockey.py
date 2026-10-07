"""Tests del procesador de Jockey (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.jockey import JockeyProcessor

proc = JockeyProcessor()
URL = "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario"


def parse(fixture, url):
    return proc.parse(fixture_text("jockey", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Jockey® Boxer Hombre Algodón Tallas Grandes - Unidad (XL / AZUL MARINO)",
        2994,
        4990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("jockey", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario"
        ),
    )
    assert len(variantes) == 7
    assert variantes[0].selected and variantes[0].variant_id == "46226722029759"
    assert variantes[0].label == "XL / AZUL MARINO: $2.994 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 1


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario?variant=46226722062527",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Jockey® Boxer Hombre Algodón Tallas Grandes - Unidad (XL / AZUL)",
        2994,
        4990,
        True,
    )


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "jockey-boxer-hombre-algodon-tallas-grandes-unitario",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario",
        "https://www.jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario",
        "http://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario/",
        "https://jockey.cl/products/JOCKEY-BOXER-HOMBRE-ALGODON-TALLAS-GRANDES-UNITARIO?utm_source=x#top",
        "https://jockey.cl/collections/hombre/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "jockey-boxer-hombre-algodon-tallas-grandes-unitario",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "jockey.cl"
    assert find_processor(URL).name == "jockey"
    assert not proc.matches("https://jockey.cl/")
    assert not proc.matches("https://jockey.cl/collections/hombre")
    assert not proc.matches("https://jockey.cl/search?q=polera")
    assert not proc.matches("https://jockey.cl/pages/tiendas")
    assert not proc.matches(
        "https://jockey.cl.evil.com/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario"
    )
    assert not proc.matches(
        "https://notjockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario"
    )
