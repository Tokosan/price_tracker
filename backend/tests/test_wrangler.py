"""Tests del procesador de Wrangler (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.wrangler import WranglerProcessor

proc = WranglerProcessor()
URL = "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light"


def parse(fixture, url):
    return proc.parse(fixture_text("wrangler", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Jeans Hombre Larston Azul medio Toughlite (US 30 - CH 42)",
        31493,
        44990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("wrangler", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light"
        ),
    )
    assert len(variantes) == 5
    assert variantes[0].selected and variantes[0].variant_id == "47655123320963"
    assert variantes[0].label == "US 30 - CH 42: $31.493 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 4


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light?variant=47655123452035",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Jeans Hombre Larston Azul medio Toughlite (US 38 - CH 50)",
        31493,
        44990,
        True,
    )


def test_descuento():
    r = parse(
        "descuento.json",
        "https://wrangler.cl/products/polera-hombre-cuello-redondo-manga-corta-regular-fit-100-cotton-negro-2",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polera Hombre Cuello Redondo Manga Corta Regular Fit 100% Cotton Negro (S)",
        10194,
        16990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
        "https://www.wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
        "http://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light/",
        "https://wrangler.cl/products/CAMISA-HOMBRE-MANGA-LARGA-LINO-1-BOLSILLO-SLIM-TAPERED-LIGHT?utm_source=x#top",
        "https://wrangler.cl/collections/hombre/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "wrangler.cl"
    assert find_processor(URL).name == "wrangler"
    assert not proc.matches("https://wrangler.cl/")
    assert not proc.matches("https://wrangler.cl/collections/hombre")
    assert not proc.matches("https://wrangler.cl/search?q=polera")
    assert not proc.matches("https://wrangler.cl/pages/tiendas")
    assert not proc.matches(
        "https://wrangler.cl.evil.com/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light"
    )
    assert not proc.matches(
        "https://notwrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light"
    )
