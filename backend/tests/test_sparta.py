"""Sparta: fichas HTML reales (Magento 2), con el `form_key` redactado."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.sparta import SpartaProcessor

sparta = SpartaProcessor()
S = "https://sparta.cl"
POLERA = (
    f"{S}/polera-running-mujer-new-balance-sport-essentials-t-shirt-negra-1690000wt41222bk21.html"
)
NOVABLAST = f"{S}/zapatillas-running-mujer-asics-novablast-6-beige-01501012c008-70022.html"
PROTECTOR = f"{S}/protector-bucal-adulto-liso-azul-safejawz-43700000sjibluea1600.html"
ATHLETICS = (
    f"{S}/polera-lifestyle-hombre-new-balance-athletics-premium-logo-t-shirt-negra-"
    "169000mt41908blk21.html"
)
MARLIN = f"{S}/bicicleta-mtb-trek-marlin-4-gen-3-negra-262533695753369721.html"
TALLA_M = "1690000WT41222BK2104"


def parse(fixture, url):
    return sparta.parse(fixture_text("sparta", fixture), sparta.normalize(url))


def test_cualquier_talla_con_descuento():
    r = parse("polera_descuento.html", POLERA)
    assert r.title == "Polera Running Mujer New Balance Sport Essentials T-Shirt Negra"
    assert (r.price, r.list_price, r.currency, r.available) == (10990, 24990, "CLP", True)
    assert r.image_url == (
        "https://sparta.cl/media/catalog/product/p/o/"
        "polera-running-mujer-new-balance-sport-essentials-t-shirt-negra-frontal.png"
    )


def test_talla_puntual():
    r = parse("polera_descuento.html", f"{POLERA}?sku={TALLA_M}")
    assert r.title == "Polera Running Mujer New Balance Sport Essentials T-Shirt Negra (talla M)"
    assert (r.price, r.list_price, r.available) == (10990, 24990, True)


def test_talla_que_desaparece_es_agotado_sin_precio():
    # Sparta saca del jsonConfig las tallas agotadas.
    r = parse("polera_descuento.html", f"{POLERA}?sku=1690000WT41222BK2199")
    assert r.title == "Polera Running Mujer New Balance Sport Essentials T-Shirt Negra"
    assert (r.price, r.available) == (None, False)
    assert sparta.sold_out_without_price is True


def test_sin_descuento_sku_con_punto():
    r = parse("zapatillas_sin_descuento.html", NOVABLAST)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zapatillas Running Mujer Asics Novablast 6 beige",
        139990,
        None,
        True,
    )
    r = parse("zapatillas_sin_descuento.html", f"{NOVABLAST}?sku=01501012c008.7002208")
    assert r.title == "Zapatillas Running Mujer Asics Novablast 6 beige (talla 36.5)"
    assert (r.price, r.list_price, r.available) == (139990, None, True)


def test_producto_simple():
    r = parse("bicicleta_simple.html", MARLIN)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Bicicleta MTB Trek Marlin 4 Gen 3 Negra",
        478900,
        599900,
        True,
    )
    raw = fixture_text("sparta", "bicicleta_simple.html")
    assert sparta.parse_variants(raw, sparta.normalize(MARLIN)) == []


def test_agotado_con_precio():
    # Un producto simple agotado conserva el precio en la ficha.
    r = parse("agotado_con_precio.html", PROTECTOR)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Protector Bucal Adulto Safejawz Azul",
        10990,
        14990,
        False,
    )


def test_agotado_sin_precio():
    # Un configurable agotado no trae precio ni jsonConfig: la marca "Agotado" lo confirma.
    r = parse("agotado_sin_precio.html", ATHLETICS)
    assert r.title == "Polera Lifestyle Hombre New Balance Athletics Premium Logo T-Shirt Negra"
    assert (r.price, r.list_price, r.available) == (None, None, False)
    r = parse("agotado_sin_precio.html", f"{ATHLETICS}?sku=169000MT41908BLK2104")
    assert (r.price, r.available) == (None, False)


def test_sin_precio_con_stock_es_error():
    raw = fixture_text("sparta", "bicicleta_simple.html").replace(
        'data-price-amount="478900"', 'data-price-amount="0"'
    )
    with pytest.raises(FetchError):
        sparta.parse(raw, sparta.normalize(MARLIN))


def test_sin_marca_de_stock_es_error():
    raw = fixture_text("sparta", "bicicleta_simple.html").replace(
        'class="product-info-stock-sku"', 'class="otra-cosa"'
    )
    with pytest.raises(FetchError):
        sparta.parse(raw, sparta.normalize(MARLIN))


def test_talla_sin_jsonconfig_con_stock_es_error():
    raw = fixture_text("sparta", "polera_descuento.html").replace('"jsonConfig":', '"otro":')
    with pytest.raises(FetchError):
        sparta.parse(raw, sparta.normalize(f"{POLERA}?sku={TALLA_M}"))


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria_hombre.html", f"{S}/hombre.html")


def test_variantes():
    raw = fixture_text("sparta", "polera_descuento.html")
    variants = sparta.parse_variants(raw, sparta.normalize(POLERA))
    assert variants[0].selected and variants[0].variant_id == ""
    assert variants[0].label == "Cualquier talla"
    assert [v.label for v in variants[1:]] == [
        "Talla XS: $10.990",
        "Talla S: $10.990",
        "Talla M: $10.990",
        "Talla L: $10.990",
        "Talla XL: $10.990",
    ]
    for v in variants:
        ref = sparta.normalize(v.url)
        assert (ref.external_id, ref.variant_id) == (v.external_id, v.variant_id)
    selected = sparta.parse_variants(raw, sparta.normalize(f"{POLERA}?sku={TALLA_M}"))
    assert selected[0].selected and selected[0].variant_id == TALLA_M


@pytest.mark.parametrize(
    ("url", "key", "sku", "canonical"),
    [
        (MARLIN, "bicicleta-mtb-trek-marlin-4-gen-3-negra-262533695753369721", "", MARLIN),
        (
            "http://www.sparta.cl/Bicicleta-MTB-Trek-Marlin-4-Gen-3-Negra-262533695753369721.html"
            "?utm_source=x#top",
            "bicicleta-mtb-trek-marlin-4-gen-3-negra-262533695753369721",
            "",
            MARLIN,
        ),
        (f"{POLERA}?sku={TALLA_M.lower()}", POLERA[18:-5], TALLA_M, f"{POLERA}?sku={TALLA_M}"),
        (f"{POLERA}?sku=<script>", POLERA[18:-5], "", POLERA),
    ],
)
def test_normaliza_url(url, key, sku, canonical):
    assert sparta.matches(url)
    ref = sparta.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (key, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://sparta.cl.evil.com/bicicleta-mtb-trek-marlin-4.html",
        "https://evilsparta.cl/bicicleta-mtb-trek-marlin-4.html",
        "https://sparta.cl/zapatillas/zapatillas-urbanas.html",
        "https://sparta.cl/catalog/category/view/id/2918",
        "https://sparta.cl/",
        "https://sparta.com/bicicleta-mtb-trek-marlin-4.html",
    ],
)
def test_no_matchea(url):
    assert not sparta.matches(url)


def test_registrado():
    assert find_processor(MARLIN).name == "sparta"
