"""Tests del procesador de Dockers (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.dockers import DockersProcessor

proc = DockersProcessor()
URL = "https://www.dockers.cl/products/reversible-leather-belt-a"


def parse(fixture, url):
    return proc.parse(fixture_text("dockers", fixture), proc.normalize(url))


def test_tallas():
    r = parse("tallas.json", "https://www.dockers.cl/products/reversible-leather-belt-a")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Cinturon reversible cuero Negro Café (32 / Negro)",
        23090,
        32990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("dockers", "tallas.json")
    variantes = proc.parse_variants(
        raw, proc.normalize("https://www.dockers.cl/products/reversible-leather-belt-a")
    )
    assert len(variantes) == 6
    assert variantes[0].selected and variantes[0].variant_id == "45055963070579"
    assert variantes[0].label == "32 / Negro: $23.090 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 5


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.dockers.cl/products/reversible-leather-belt-a?variant=45055963168883",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Cinturon reversible cuero Negro Café (38 / Negro)",
        23090,
        32990,
        True,
    )


def test_agotado():
    r = parse(
        "agotado.json", "https://www.dockers.cl/products/poleron-1-4-zip-fleece-beautiful-black"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Poleron 1/4 Zip Fleece Beautiful Black (S / Negro)",
        22490,
        44990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "reversible-leather-belt-a",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dockers.cl/products/reversible-leather-belt-a",
        "https://dockers.cl/products/reversible-leather-belt-a",
        "http://www.dockers.cl/products/reversible-leather-belt-a/",
        "https://www.dockers.cl/products/REVERSIBLE-LEATHER-BELT-A?utm_source=x#top",
        "https://www.dockers.cl/collections/hombre/products/reversible-leather-belt-a",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "reversible-leather-belt-a",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.dockers.cl"
    assert find_processor(URL).name == "dockers"
    assert not proc.matches("https://www.dockers.cl/")
    assert not proc.matches("https://www.dockers.cl/collections/hombre")
    assert not proc.matches("https://www.dockers.cl/search?q=polera")
    assert not proc.matches("https://www.dockers.cl/pages/tiendas")
    assert not proc.matches("https://dockers.cl.evil.com/products/reversible-leather-belt-a")
    assert not proc.matches("https://notdockers.cl/products/reversible-leather-belt-a")
