"""Tests del procesador de B-Soul (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.bsoul import BSoulProcessor

proc = BSoulProcessor()
URL = "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11"


def parse(fixture, url):
    return proc.parse(fixture_text("bsoul", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polera Mujer Anto Aloe Negra Bsoul (XS)",
        18990,
        29990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("bsoul", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11"
        ),
    )
    assert len(variantes) == 5
    assert variantes[0].selected and variantes[0].variant_id == "47445456781499"
    assert variantes[0].label == "XS: $18.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 3


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11?variant=47445456814267",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polera Mujer Anto Aloe Negra Bsoul (S)",
        18990,
        29990,
        True,
    )


def test_agotado():
    r = parse(
        "agotado.json", "https://www.bsoul.com/products/peto-mujer-elisa-bsoul-bs290021161-db3"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Peto Mujer Elisa Azul Bsoul (XS)",
        29990,
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
        "polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
        "https://bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
        "http://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11/",
        "https://www.bsoul.com/products/POLERA-M-C-MUJER-T-SHIRT-ANTO-ALOE-BSOUL-BS210021859-N11?utm_source=x#top",
        "https://www.bsoul.com/collections/hombre/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.bsoul.com"
    assert find_processor(URL).name == "bsoul"
    assert not proc.matches("https://www.bsoul.com/")
    assert not proc.matches("https://www.bsoul.com/collections/hombre")
    assert not proc.matches("https://www.bsoul.com/search?q=polera")
    assert not proc.matches("https://www.bsoul.com/pages/tiendas")
    assert not proc.matches(
        "https://bsoul.com.evil.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11"
    )
    assert not proc.matches(
        "https://notbsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11"
    )
