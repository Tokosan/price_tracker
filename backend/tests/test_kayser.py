"""Tests del procesador de Kayser (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.kayser import KayserProcessor

proc = KayserProcessor()
URL = "https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado"


def parse(fixture, url):
    return proc.parse(fixture_text("kayser", fixture), proc.normalize(url))


def test_tallas():
    r = parse("tallas.json", "https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "TRIPACK KAYSER PANTALETA DE ALGODÓN ROSADO TEENS MUJER (10)",
        6299,
        8999,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("kayser", "tallas.json")
    variantes = proc.parse_variants(
        raw, proc.normalize("https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado")
    )
    assert len(variantes) == 4
    assert variantes[0].selected and variantes[0].variant_id == "54455701831990"
    assert variantes[0].label == "10: $6.299 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 1


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado?variant=54455701864758",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "TRIPACK KAYSER PANTALETA DE ALGODÓN ROSADO TEENS MUJER (12)",
        6299,
        8999,
        True,
    )


def test_descuento():
    r = parse("descuento.json", "https://kaysershop.com/products/sosten-soft-p350024-negro6")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "TRIPACK SOSTÉN SOFT DE ALGODÓN NEGRO DE MUJER (36 / C)",
        14699,
        20999,
        "CLP",
        True,
    )


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "calzon-pantaletas-p315-7095-rosado",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado",
        "https://www.kaysershop.com/products/calzon-pantaletas-p315-7095-rosado",
        "http://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado/",
        "https://kaysershop.com/products/CALZON-PANTALETAS-P315-7095-ROSADO?utm_source=x#top",
        "https://kaysershop.com/collections/hombre/products/calzon-pantaletas-p315-7095-rosado",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "calzon-pantaletas-p315-7095-rosado",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "kaysershop.com"
    assert find_processor(URL).name == "kayser"
    assert not proc.matches("https://kaysershop.com/")
    assert not proc.matches("https://kaysershop.com/collections/hombre")
    assert not proc.matches("https://kaysershop.com/search?q=polera")
    assert not proc.matches("https://kaysershop.com/pages/tiendas")
    assert not proc.matches(
        "https://kaysershop.com.evil.com/products/calzon-pantaletas-p315-7095-rosado"
    )
    assert not proc.matches("https://notkaysershop.com/products/calzon-pantaletas-p315-7095-rosado")
