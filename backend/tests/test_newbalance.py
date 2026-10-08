"""New Balance: fichas HTML reales (Magento 2; el stock es el botón de compra)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.newbalance import NewBalanceProcessor

nb = NewBalanceProcessor()
S = "https://newbalance.cl"
Z530 = f"{S}/zapatillas-urbanas-unisex-new-balance-530-bicolor-169000000mr530sg96.html"
Z996 = f"{S}/zapatillas-tenis-hombre-new-balance-996-v6-clay-azul-16900000mcy996f616.html"
JOCKEY = (
    f"{S}/jockey-running-unisex-new-balance-classic-nb-curved-brim-negro-169000lah91014bk2103.html"
)
GORRO = f"{S}/gorro-lifestyle-unisex-new-balance-negro-169000lah51020bk2100.html"
POLERA = f"{S}/polera-lifestyle-hombre-new-balance-woven-label-negro-1690000mt53928bk21.html"


def parse(fixture, url):
    return nb.parse(fixture_text("newbalance", fixture), nb.normalize(url))


def test_tallas():
    r = parse("zapatillas_tallas.html", Z530)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zapatillas Urbanas Unisex New Balance 530 Bicolor",
        99990,
        None,
        True,
    )
    r = parse("zapatillas_tallas.html", f"{Z530}?sku=169000000MR530SG9623")
    assert r.title == "Zapatillas Urbanas Unisex New Balance 530 Bicolor (talla H4.5 / M6)"
    raw = fixture_text("newbalance", "zapatillas_tallas.html")
    variants = nb.parse_variants(raw, nb.normalize(Z530))
    assert len(variants) == 16
    assert variants[1].label == "Talla H4 / M5.5: $99.990"


def test_descuento():
    r = parse("zapatillas_descuento.html", Z996)
    assert (r.price, r.list_price, r.available) == (59990, 129990, True)


def test_simple_con_stock():
    r = parse("jockey_simple.html", JOCKEY)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Jockey Unisex New Balance Classic NB Curved Brim Negro",
        9990,
        16990,
        True,
    )


def test_agotados():
    # Sin botón de compra (el formulario sigue): agotado.
    r = parse("agotado_con_precio.html", GORRO)
    assert (r.price, r.list_price, r.available) == (9990, 19990, False)
    r = parse("agotado_sin_precio.html", POLERA)
    assert (r.price, r.available) == (None, False)


def test_sin_formulario_es_error():
    raw = fixture_text("newbalance", "jockey_simple.html").replace(
        'id="product_addtocart_form"', 'id="otro"'
    )
    with pytest.raises(FetchError):
        nb.parse(raw, nb.normalize(JOCKEY))


def test_no_es_producto():
    with pytest.raises(NotFoundError):
        nb.parse('<meta property="og:type" content="website" />', nb.normalize(JOCKEY))


@pytest.mark.parametrize(
    "url",
    [
        "https://newbalance.cl.evil.com/jockey.html",
        "https://newbalance.com/jockey.html",
        "https://newbalance.cl/hombre/zapatillas.html",
    ],
)
def test_no_matchea(url):
    assert not nb.matches(url)


def test_registrado():
    assert find_processor(Z530).name == "newbalance"
