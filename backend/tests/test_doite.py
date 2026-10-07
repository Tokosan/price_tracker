"""Tests del procesador de Doite (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.doite import DoiteProcessor

proc = DoiteProcessor()
URL = "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite"


def parse(fixture, url):
    return proc.parse(fixture_text("doite", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json", "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polera Manga Corta Mountain Logo Hombre Doite (Blanco / XS)",
        16990,
        None,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("doite", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite"
        ),
    )
    assert len(variantes) == 48
    assert variantes[0].selected and variantes[0].variant_id == "47068343009495"
    assert variantes[0].label == "Blanco / XS: $16.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 36


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite?variant=47068343763159",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polera Manga Corta Mountain Logo Hombre Doite (Oliva / XXL)",
        16990,
        None,
        True,
    )


def test_descuento():
    r = parse("descuento.json", "https://www.doite.cl/products/peludo-wooly-hombre-doite")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Peludo Wooly Hombre Doite (Azul Marino / S)",
        35990,
        59990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json", "https://www.doite.cl/products/bandana-aerowarm-velocity-unisex-doite"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Bandana Aerowarm Velocity Unisex Doite",
        15990,
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
        "polera-manga-corta-mountain-logo-hombre-doite",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite",
        "https://doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite",
        "http://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite/",
        "https://www.doite.cl/products/POLERA-MANGA-CORTA-MOUNTAIN-LOGO-HOMBRE-DOITE?utm_source=x#top",
        "https://www.doite.cl/collections/hombre/products/polera-manga-corta-mountain-logo-hombre-doite",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "polera-manga-corta-mountain-logo-hombre-doite",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.doite.cl"
    assert find_processor(URL).name == "doite"
    assert not proc.matches("https://www.doite.cl/")
    assert not proc.matches("https://www.doite.cl/collections/hombre")
    assert not proc.matches("https://www.doite.cl/search?q=polera")
    assert not proc.matches("https://www.doite.cl/pages/tiendas")
    assert not proc.matches(
        "https://doite.cl.evil.com/products/polera-manga-corta-mountain-logo-hombre-doite"
    )
    assert not proc.matches(
        "https://notdoite.cl/products/polera-manga-corta-mountain-logo-hombre-doite"
    )
