import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.salcobrand import SalcobrandProcessor

sb = SalcobrandProcessor()
BASE = "https://salcobrand.cl/products/"
COLGATE = BASE + "pasta-dental-colgate-total-interdental-90-g"
MINFEL = BASE + "minfel-b-metilfenidato-36mg-30-comprimidos-prolongados"
BROPAVOL = BASE + "bropavol-bromhexina-8mg-5ml-jarabe-100ml"
MASCARA = BASE + "mascara-de-pestanas-colossal-indestructible-contra-agua"


def parse(fixture, url):
    return sb.parse(fixture_text("salcobrand", fixture), sb.normalize(url))


def test_descuento_usa_precio_internet_e_ignora_sbpay():
    raw = fixture_text("salcobrand", "descuento_pasta_colgate.html")
    # Precio Farmacia 4.499 (también en og:price:amount) y Precio SBPay 2.519.
    assert '"name":"Precio SBPay","price":2519' in raw
    assert 'og:price:amount" content="4499.0"' in raw
    r = sb.parse(raw, sb.normalize(COLGATE))
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Pasta Dental Colgate Total Interdental 90 g",
        2969,
        4499,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://static.salcobrand.cl/spree/products/")


def test_medicamento_con_receta_retenida():
    raw = fixture_text("salcobrand", "receta_retenida_minfel.html")
    assert "https://schema.org/PrescriptionOnly" in raw
    r = sb.parse(raw, sb.normalize(MINFEL))
    assert r.title == "Minfel (B) Metilfenidato 36mg 30 Comprimidos Prolongados"
    assert (r.price, r.list_price, r.available) == (62743, 71299, True)


def test_medicamento_sin_receta():
    raw = fixture_text("salcobrand", "venta_directa_bropavol.html")
    assert "https://schema.org/OTC" in raw
    r = sb.parse(raw, sb.normalize(BROPAVOL))
    assert r.title == "Bropavol Bromhexina 8mg/5ml Jarabe 100ml"
    assert (r.price, r.list_price, r.available) == (4839, 5499, True)


def test_variantes_con_la_misma_etiqueta_y_precio_propio():
    # Metotrexato (receta médica): dos SKU "100 Comprimidos" con precios distintos.
    url = BASE + "metotrexato?default_sku=3256037"
    raw = fixture_text("salcobrand", "variantes_metotrexato_sku_3256037.html")
    r = sb.parse(raw, sb.normalize(url))
    assert r.title == "Metotrexato (R) 2.5mg 100 Comprimidos (100 Comprimidos, SKU 3256037)"
    assert (r.price, r.list_price, r.available) == (36783, 41799, True)
    assert [(v.variant_id, v.label) for v in sb.parse_variants(raw, sb.normalize(url))] == [
        ("3256037", "100 Comprimidos, SKU 3256037: $36.783"),
        ("2200137", "100 Comprimidos, SKU 2200137: $30.975"),
    ]


def test_variantes_sin_sku_sigue_la_primera_que_esta_descontinuada():
    r = parse("variantes_mascara.html", MASCARA)
    # Sin precio tachado (sin descuento) y `availability` Discontinued: agotado.
    assert r.title == (
        "Mascara de Pestañas Colossal Indestructible Contra Agua (Negro, 1 Unidad, SKU 5840554)"
    )
    assert (r.price, r.list_price, r.available) == (9099, None, False)


def test_default_sku_cambia_el_json_ld():
    r = parse("variantes_mascara_sku_4845262.html", MASCARA + "?default_sku=4845262")
    assert r.title.endswith("(Negro, 1 Unidad, SKU 4845262)")
    assert (r.price, r.list_price, r.available) == (11999, None, True)


def test_sku_que_ya_no_es_del_producto_no_lee_otra_variante():
    # Con un SKU ajeno la tienda muestra la primera variante sin dar error.
    with pytest.raises(NotFoundError, match="999999"):
        parse("variantes_mascara.html", MASCARA + "?default_sku=999999")
    with pytest.raises(NotFoundError):
        parse("variantes_mascara_sku_4845262.html", MASCARA + "?default_sku=5840554")


def test_variantes_de_la_ficha():
    raw = fixture_text("salcobrand", "variantes_mascara.html")
    variants = sb.parse_variants(raw, sb.normalize(MASCARA))
    assert [(v.variant_id, v.label, v.selected) for v in variants] == [
        ("5840554", "Negro, 1 Unidad, SKU 5840554: $9.099 (agotada)", True),
        ("4845262", "Negro, 1 Unidad, SKU 4845262: $11.999", False),
    ]
    assert variants[1].url == MASCARA + "?default_sku=4845262"
    assert {v.external_id for v in variants} == {
        "mascara-de-pestanas-colossal-indestructible-contra-agua"
    }


def test_variantes_con_sku_marca_la_del_link():
    url = MASCARA + "?default_sku=4845262"
    raw = fixture_text("salcobrand", "variantes_mascara_sku_4845262.html")
    variants = sb.parse_variants(raw, sb.normalize(url))
    assert [(v.variant_id, v.selected) for v in variants] == [("4845262", True), ("5840554", False)]
    assert variants[0].url == url


def test_una_sola_variante_se_ofrece_sin_sku():
    raw = fixture_text("salcobrand", "descuento_pasta_colgate.html")
    for url in (COLGATE, COLGATE + "?default_sku=595820"):
        variants = sb.parse_variants(raw, sb.normalize(url))
        assert [(v.url, v.variant_id, v.label, v.selected) for v in variants] == [
            (COLGATE, "", "90g", True)
        ]


def test_sin_product_en_el_json_ld_es_error_de_lectura():
    raw = fixture_text("salcobrand", "descuento_pasta_colgate.html").replace(
        '"@type":"Product"', '"@type":"Cosa"'
    )
    with pytest.raises(FetchError):
        sb.parse(raw, sb.normalize(COLGATE))
    with pytest.raises(FetchError):
        parse("no_existe.html", COLGATE)


def test_sin_tachado_mayor_no_hay_list_price():
    raw = fixture_text("salcobrand", "descuento_pasta_colgate.html").replace(
        '"price":4499,', '"price":2969,'
    )
    r = sb.parse(raw, sb.normalize(COLGATE))
    assert (r.price, r.list_price) == (2969, None)


@pytest.mark.parametrize(
    "url",
    [
        COLGATE,
        "http://salcobrand.cl/products/pasta-dental-colgate-total-interdental-90-g/",
        "https://www.salcobrand.cl/products/Pasta-Dental-Colgate-Total-Interdental-90-G",
        COLGATE + "?utm_source=wa&default_sku=abc#tab",
    ],
)
def test_normaliza_url(url):
    ref = sb.normalize(url)
    assert (ref.external_id, ref.variant_id) == ("pasta-dental-colgate-total-interdental-90-g", "")
    assert ref.canonical_url == COLGATE


def test_normaliza_url_con_variante():
    ref = sb.normalize(
        "https://www.salcobrand.cl/products/mascara-de-pestanas-colossal-indestructible-contra-agua"
        "?utm_medium=x&default_sku=4845262"
    )
    assert (ref.external_id, ref.variant_id) == (
        "mascara-de-pestanas-colossal-indestructible-contra-agua",
        "4845262",
    )
    assert ref.canonical_url == MASCARA + "?default_sku=4845262"


def test_matchea_solo_fichas_de_salcobrand():
    assert find_processor(COLGATE).name == "salcobrand"
    assert find_processor("https://www.salcobrand.cl/products/x-1").name == "salcobrand"
    assert not sb.matches("https://salcobrand.cl/")
    assert not sb.matches("https://salcobrand.cl/products")
    assert not sb.matches("https://salcobrand.cl/products/")
    assert not sb.matches("https://salcobrand.cl/t/medicamentos")
    assert not sb.matches("https://salcobrand.cl/campaigns/cyber")
    assert not sb.matches("https://salcobrand.cl/products/a/b")
    assert not sb.matches("https://salcobrand.cl.evil.com/products/pasta-dental")
    assert not sb.matches("https://evilsalcobrand.cl/products/pasta-dental")
    assert not sb.matches("https://preunic.cl/products/pasta-dental")
    assert not sb.matches("ftp://salcobrand.cl/products/pasta-dental")
    with pytest.raises(ValueError):
        sb.normalize("https://salcobrand.cl/t/medicamentos")
