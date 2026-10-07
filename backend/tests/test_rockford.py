"""Tests del procesador de Rockford (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.rockford import RockfordProcessor

proc = RockfordProcessor()
URL = "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4"


def parse(fixture, url):
    return proc.parse(fixture_text("rockford", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Blusa Algodón Orgánico Mujer Petunia Café Rockford (XS)",
        39995,
        79990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("rockford", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4"
        ),
    )
    assert len(variantes) == 5
    assert variantes[0].selected and variantes[0].variant_id == "43707326922788"
    assert variantes[0].label == "XS: $39.995 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 4


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4?variant=43707327053860",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Blusa Algodón Orgánico Mujer Petunia Café Rockford (XL)",
        39995,
        79990,
        True,
    )


def test_descuento():
    r = parse(
        "descuento.json",
        "https://www.rkflife.com/products/calcetin-mujer-rfv25w-st-dalia-rockford-rk210031977-6pv",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Calcetin Bambú Mujer St Dalia Morado Rockford",
        4495,
        8990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.rkflife.com/products/zapatilla-hombre-crestwood-low-columbia-1781181-hhc",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatilla Hombre Crestwood Low Azul Columbia (40)",
        55993,
        79990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
        "https://rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
        "http://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4/",
        "https://www.rkflife.com/products/BLUSA-MANGA-LARGA-MUJER-BLS-PETUNIA-AW26-ROCKFORD-RK210021679-PO4?utm_source=x#top",
        "https://www.rkflife.com/collections/hombre/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.rkflife.com"
    assert find_processor(URL).name == "rockford"
    assert not proc.matches("https://www.rkflife.com/")
    assert not proc.matches("https://www.rkflife.com/collections/hombre")
    assert not proc.matches("https://www.rkflife.com/search?q=polera")
    assert not proc.matches("https://www.rkflife.com/pages/tiendas")
    assert not proc.matches(
        "https://rkflife.com.evil.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4"
    )
    assert not proc.matches(
        "https://notrkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4"
    )
