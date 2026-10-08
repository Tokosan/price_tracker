"""Head: fichas HTML reales (Magento 2, selector clásico con `spConfig`)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.head import HeadProcessor

head = HeadProcessor()
S = "https://head.cl"
RAQUETA = f"{S}/raqueta-tenis-head-speed-mp-legend-2025-negra-104000000023207621.html"
GRIP = f"{S}/grip-tenis-head-prime-tour-naranja-10400000285621240400.html"
ZAPATILLAS = f"{S}/zapatillas-tenis-mujer-head-sprint-pro-3-5-clay-blanca-104000000027417301.html"


def parse(fixture, url):
    return head.parse(fixture_text("head", fixture), head.normalize(url))


def test_raqueta_con_descuento_y_un_grip_vendible():
    # Grip 2 agotado (products: []) y grip 3 con stock: solo queda una opción.
    r = parse("raqueta_grip_descuento.html", RAQUETA)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Raqueta Tenis Head Speed MP Legend 2025 Negra",
        244990,
        289990,
        True,
    )
    r = parse("raqueta_grip_descuento.html", f"{RAQUETA}?sku=10400000002320762110")
    assert r.title == "Raqueta Tenis Head Speed MP Legend 2025 Negra (talla 3)"
    assert (r.price, r.available) == (244990, True)
    raw = fixture_text("head", "raqueta_grip_descuento.html")
    assert head.parse_variants(raw, head.normalize(RAQUETA)) == []


def test_agotados():
    r = parse("agotado_con_precio.html", GRIP)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Grip Tenis Head Prime Tour Naranja",
        8990,
        None,
        False,
    )
    r = parse("agotado_sin_precio.html", ZAPATILLAS)
    assert (r.price, r.available) == (None, False)


def test_no_es_producto():
    with pytest.raises(NotFoundError):
        head.parse('<meta property="og:type" content="website" />', head.normalize(RAQUETA))


@pytest.mark.parametrize(
    "url",
    [
        "https://head.cl.evil.com/grip.html",
        "https://ahead.cl/grip.html",
        "https://head.cl/a/b.html",
    ],
)
def test_no_matchea(url):
    assert not head.matches(url)


def test_registrado():
    assert find_processor(RAQUETA).name == "head"
