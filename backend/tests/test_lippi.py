"""Tests del procesador de Lippi (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.lippi import LippiProcessor

proc = LippiProcessor()
URL = "https://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu"


def parse(fixture, url):
    return proc.parse(fixture_text("lippi", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json", "https://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polar Mujer Ruil Negro Haka Honu (XS)",
        29990,
        42990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("lippi", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize("https://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu"),
    )
    assert len(variantes) == 6
    assert variantes[0].selected and variantes[0].variant_id == "50747188347201"
    assert variantes[0].label == "XS: $29.990"
    assert sum("(agotada)" in v.label for v in variantes) == 5


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "polar-mujer-ruil-negro-haka-honu",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu",
        "https://lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu",
        "http://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu/",
        "https://www.lippioutdoor.com/products/POLAR-MUJER-RUIL-NEGRO-HAKA-HONU?utm_source=x#top",
        "https://www.lippioutdoor.com/collections/hombre/products/polar-mujer-ruil-negro-haka-honu",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "polar-mujer-ruil-negro-haka-honu",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.lippioutdoor.com"
    assert find_processor(URL).name == "lippi"
    assert not proc.matches("https://www.lippioutdoor.com/")
    assert not proc.matches("https://www.lippioutdoor.com/collections/hombre")
    assert not proc.matches("https://www.lippioutdoor.com/search?q=polera")
    assert not proc.matches("https://www.lippioutdoor.com/pages/tiendas")
    assert not proc.matches(
        "https://lippioutdoor.com.evil.com/products/polar-mujer-ruil-negro-haka-honu"
    )
    assert not proc.matches("https://notlippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu")
