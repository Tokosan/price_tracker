"""Speedo: fichas HTML reales (Magento 2, tema con `<p class="availability …">`)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.speedo import SpeedoProcessor

speedo = SpeedoProcessor()
S = "https://speedo.cl"
TRAJE = (
    f"{S}/traje-de-bano-natacion-mujer-speedo-training-comfort-v-back-rosado-"
    "24208-a00030000506.html"
)
SPLASH = f"{S}/traje-de-ba-o-ni-a-speedo-allover-splashback-multicolor-242080026231677921.html"
GORRO = f"{S}/gorro-natacion-speedo-long-hair-cap-multicolor-24200811306159749900.html"


def parse(fixture, url):
    return speedo.parse(fixture_text("speedo", fixture), speedo.normalize(url))


def test_cualquier_talla_y_talla_puntual():
    title = "Traje de Baño Natación Mujer Speedo Training Comfort V-Back Rosado"
    r = parse("traje_tallas.html", TRAJE)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        title,
        64990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://speedo.cl/media/catalog/product/")
    r = parse("traje_tallas.html", f"{TRAJE}?sku=24208-A0003000050605")
    assert (r.title, r.price, r.available) == (f"{title} (talla 30)", 64990, True)
    r = parse("traje_tallas.html", f"{TRAJE}?sku=24208-A0003000050699")
    assert (r.price, r.available) == (None, False)


def test_variantes():
    raw = fixture_text("speedo", "traje_tallas.html")
    labels = [v.label for v in speedo.parse_variants(raw, speedo.normalize(TRAJE))]
    assert labels[:3] == ["Cualquier talla", "Talla 28: $64.990", "Talla 30: $64.990"]
    assert len(labels) == 7


def test_agotados():
    r = parse("agotado_sin_precio.html", SPLASH)
    assert r.title == "Traje de Baño Niña Speedo Allover Splashback Multicolor"
    assert (r.price, r.available) == (None, False)
    r = parse("agotado_con_precio.html", GORRO)
    assert (r.price, r.list_price, r.available) == (8495, 16990, False)


def test_sin_marca_de_stock_es_error():
    raw = fixture_text("speedo", "traje_tallas.html").replace(
        '<p class="availability in-stock">', "<p>"
    )
    with pytest.raises(FetchError):
        speedo.parse(raw, speedo.normalize(TRAJE))


def test_no_es_producto():
    with pytest.raises(NotFoundError):
        speedo.parse('<meta property="og:type" content="website" />', speedo.normalize(TRAJE))


@pytest.mark.parametrize(
    "url",
    [
        "https://speedo.cl.evil.com/gorro.html",
        "https://evilspeedo.cl/gorro.html",
        "https://speedo.cl/natacion/trajes.html",
        "https://speedo.com/gorro.html",
    ],
)
def test_no_matchea(url):
    assert not speedo.matches(url)


def test_registrado():
    assert find_processor(f"http://www.speedo.cl/{TRAJE[18:]}").name == "speedo"
    assert speedo.normalize(f"http://www.speedo.cl/{TRAJE[18:]}").canonical_url == TRAJE
