"""Tests del procesador de Crocs (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.crocs import CrocsProcessor

proc = CrocsProcessor()
URL = "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1"


def parse(fixture, url):
    return proc.parse(fixture_text("crocs", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zueco Unisex One Piece Thousand Sunny Multicolor Crocs (4W6)",
        47990,
        79990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("crocs", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1"
        ),
    )
    assert len(variantes) == 8
    assert variantes[0].selected and variantes[0].variant_id == "54025401303354"
    assert variantes[0].label == "4W6: $47.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 7


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1?variant=54025401368890",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zueco Unisex One Piece Thousand Sunny Multicolor Crocs (6W8)",
        47990,
        79990,
        True,
    )


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
        "https://crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
        "http://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1/",
        "https://www.crocs.cl/products/SUECO-UNISEX-ONEPIECE-TSUNNY-CLS-CROCS-212126-90H-349-1?utm_source=x#top",
        "https://www.crocs.cl/collections/hombre/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.crocs.cl"
    assert find_processor(URL).name == "crocs"
    assert not proc.matches("https://www.crocs.cl/")
    assert not proc.matches("https://www.crocs.cl/collections/hombre")
    assert not proc.matches("https://www.crocs.cl/search?q=polera")
    assert not proc.matches("https://www.crocs.cl/pages/tiendas")
    assert not proc.matches(
        "https://crocs.cl.evil.com/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1"
    )
    assert not proc.matches(
        "https://notcrocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1"
    )
