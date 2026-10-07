"""Tests del procesador de Hush Puppies (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.hushpuppies import HushPuppiesProcessor

proc = HushPuppiesProcessor()
URL = "https://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551"


def parse(fixture, url):
    return proc.parse(fixture_text("hushpuppies", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Mocasin Cuero Hombre Kent Burdeo (39)",
        59994,
        99990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("hushpuppies", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551"
        ),
    )
    assert len(variantes) == 7
    assert variantes[0].selected and variantes[0].variant_id == "47514370179246"
    assert variantes[0].label == "39: $59.994"
    assert sum("(agotada)" in v.label for v in variantes) == 6


def test_descuento():
    r = parse(
        "descuento.json",
        "https://www.hushpuppies.cl/products/calcetin-algodon-mujer-c-amour-verde-hush-puppies",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Calcetin Algodón Mujer C Amour Verde Hush Puppies",
        4194,
        6990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.hushpuppies.cl/products/cartera-mujer-v25cd-ethan-cross-accesorios-hp-ha2020311196-n11",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Cartera Cuero Mujer Ethan Cross Negro Hush Puppies",
        107994,
        179990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "mocasin-hombre-kent-hush-puppies-hp10201162689-551",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551",
        "https://hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551",
        "http://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551/",
        "https://www.hushpuppies.cl/products/MOCASIN-HOMBRE-KENT-HUSH-PUPPIES-HP10201162689-551?utm_source=x#top",
        "https://www.hushpuppies.cl/collections/hombre/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "mocasin-hombre-kent-hush-puppies-hp10201162689-551",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.hushpuppies.cl"
    assert find_processor(URL).name == "hushpuppies"
    assert not proc.matches("https://www.hushpuppies.cl/")
    assert not proc.matches("https://www.hushpuppies.cl/collections/hombre")
    assert not proc.matches("https://www.hushpuppies.cl/search?q=polera")
    assert not proc.matches("https://www.hushpuppies.cl/pages/tiendas")
    assert not proc.matches(
        "https://hushpuppies.cl.evil.com/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551"
    )
    assert not proc.matches(
        "https://nothushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551"
    )
