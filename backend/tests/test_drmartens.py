"""Tests del procesador de Dr. Martens (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.drmartens import DrMartensProcessor

proc = DrMartensProcessor()
URL = "https://drmartens.cl/products/unisex-originals-boots-arcadia-1460"


def parse(fixture, url):
    return proc.parse(fixture_text("drmartens", fixture), proc.normalize(url))


def test_tallas():
    r = parse("tallas.json", "https://drmartens.cl/products/unisex-originals-boots-arcadia-1460")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Botas 1460 de cuero Arcadia (36 CL)",
        139300,
        199000,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("drmartens", "tallas.json")
    variantes = proc.parse_variants(
        raw, proc.normalize("https://drmartens.cl/products/unisex-originals-boots-arcadia-1460")
    )
    assert len(variantes) == 9
    assert variantes[0].selected and variantes[0].variant_id == "47460668637410"
    assert variantes[0].label == "36 CL: $139.300"
    assert sum("(agotada)" in v.label for v in variantes) == 1


def test_descuento():
    r = parse("descuento.json", "https://drmartens.cl/products/kasey-lo-black-virginia")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Botas Kasey Lo de cuero Virginia con tacón (36 CL)",
        175200,
        219000,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "unisex-originals-boots-arcadia-1460",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://drmartens.cl/products/unisex-originals-boots-arcadia-1460",
        "https://www.drmartens.cl/products/unisex-originals-boots-arcadia-1460",
        "http://drmartens.cl/products/unisex-originals-boots-arcadia-1460/",
        "https://drmartens.cl/products/UNISEX-ORIGINALS-BOOTS-ARCADIA-1460?utm_source=x#top",
        "https://drmartens.cl/collections/hombre/products/unisex-originals-boots-arcadia-1460",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "unisex-originals-boots-arcadia-1460",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "drmartens.cl"
    assert find_processor(URL).name == "drmartens"
    assert not proc.matches("https://drmartens.cl/")
    assert not proc.matches("https://drmartens.cl/collections/hombre")
    assert not proc.matches("https://drmartens.cl/search?q=polera")
    assert not proc.matches("https://drmartens.cl/pages/tiendas")
    assert not proc.matches(
        "https://drmartens.cl.evil.com/products/unisex-originals-boots-arcadia-1460"
    )
    assert not proc.matches("https://notdrmartens.cl/products/unisex-originals-boots-arcadia-1460")
