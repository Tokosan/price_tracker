"""Tests del procesador de Gotta (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.gotta import GottaProcessor

proc = GottaProcessor()
URL = "https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221"


def parse(fixture, url):
    return proc.parse(fixture_text("gotta", fixture), proc.normalize(url))


def test_tallas():
    r = parse("tallas.json", "https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Sandalia Plataforma Negro Mujer 13221 (35 / Negro)",
        17990,
        27990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("gotta", "tallas.json")
    variantes = proc.parse_variants(
        raw, proc.normalize("https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221")
    )
    assert len(variantes) == 6
    assert variantes[0].selected and variantes[0].variant_id == "44559202156715"
    assert variantes[0].label == "35 / Negro: $17.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 5


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221?variant=44559202189483",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Sandalia Plataforma Negro Mujer 13221 (36 / Negro)",
        17990,
        27990,
        True,
    )


def test_agotado():
    r = parse("agotado.json", "https://gotta.cl/products/sandalia-plataforma-negra-mujer-lia")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Sandalia Plataforma Negra Mujer Lia (35 / Negro)",
        37990,
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
        "sandalia-plataforma-negro-mujer-13221",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221",
        "https://www.gotta.cl/products/sandalia-plataforma-negro-mujer-13221",
        "http://gotta.cl/products/sandalia-plataforma-negro-mujer-13221/",
        "https://gotta.cl/products/SANDALIA-PLATAFORMA-NEGRO-MUJER-13221?utm_source=x#top",
        "https://gotta.cl/collections/hombre/products/sandalia-plataforma-negro-mujer-13221",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "sandalia-plataforma-negro-mujer-13221",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "gotta.cl"
    assert find_processor(URL).name == "gotta"
    assert not proc.matches("https://gotta.cl/")
    assert not proc.matches("https://gotta.cl/collections/hombre")
    assert not proc.matches("https://gotta.cl/search?q=polera")
    assert not proc.matches("https://gotta.cl/pages/tiendas")
    assert not proc.matches(
        "https://gotta.cl.evil.com/products/sandalia-plataforma-negro-mujer-13221"
    )
    assert not proc.matches("https://notgotta.cl/products/sandalia-plataforma-negro-mujer-13221")
