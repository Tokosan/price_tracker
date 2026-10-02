import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.easy import EasyProcessor
from tracker.rules import Reading, check_anomaly

easy = EasyProcessor()
BASE = "https://www.easy.cl"
CORTINA_SLUG = "cortina-blackout-100-casatua-set-2-panos-220x135cm-engomada-mkss3ko1gy"
CORTINA = f"{BASE}/{CORTINA_SLUG}/p"
PETRA = f"{BASE}/silla-de-comer-petra-mku30n0xaq/p"
BILBAO = f"{BASE}/silla-de-comer-bilbao-mkgi6cty6l/p"


def parse(fixture, url):
    return easy.parse(fixture_text("easy", fixture), easy.normalize(url))


def variants(fixture, url):
    return easy.parse_variants(fixture_text("easy", fixture), easy.normalize(url))


def test_en_stock():
    r = parse("arena_en_stock.json", f"{BASE}/arena-aglutinante-para-gatos-hey-20kg-1526501/p")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Arena sanitaria gato 20 kg",
        14990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://easycl.vteximg.com.br/")


def test_descuento_trae_precio_antes():
    url = f"{BASE}/bateria-55ah-330cca-derecho-qs55-quick-start-1258746/p"
    r = parse("bateria_descuento.json", url)
    assert r.title == "Batería 55AH 330CCA derecho QS55 Quick Start"
    assert (r.price, r.list_price, r.available) == (35990, 47990, True)


def test_agotado_con_precio():
    r = parse("chipeador_agotado.json", f"{BASE}/chipeador-match-4-13-hp-420-cc-1502715/p")
    assert (r.price, r.list_price, r.available) == (13500, None, False)


ARENA = f"{BASE}/arena-aglutinante-para-gatos-hey-20kg-1526501/p"


@pytest.mark.parametrize("url", [ARENA, f"{ARENA}?skuId=514286"])
def test_producto_simple_se_ofrece_sin_skuid(url):
    # Con o sin ?skuId= en el link, la única opción es la URL limpia con variant_id "":
    # AddWatch agrega esa, así que los dos links terminan en el mismo Product.
    vs = variants("arena_en_stock.json", url)
    assert [(v.url, v.external_id, v.variant_id, v.selected) for v in vs] == [
        (ARENA, "arena-aglutinante-para-gatos-hey-20kg-1526501", "", True)
    ]


def test_producto_simple_con_skuid_ajeno_no_existe():
    with pytest.raises(NotFoundError):
        variants("arena_en_stock.json", f"{ARENA}?skuId=999")


def test_sin_skuid_sigue_el_primer_color():
    r = parse("cortina_7_colores.json", CORTINA)
    assert r.title == "Cortina Blackout 100% Casatua Set 2 Paños 220x135cm Engomada (Negro)"
    assert (r.price, r.list_price, r.available) == (11990, 13990, True)


def test_skuid_elige_el_color():
    r = parse("cortina_7_colores.json", f"{CORTINA}?skuId=768558")
    assert r.title.endswith("(Blanco)")
    assert (r.price, r.available) == (11990, True)


def test_selector_de_colores_con_skuid_en_la_url():
    vs = variants("cortina_7_colores.json", CORTINA)
    assert [v.label.split(":")[0] for v in vs] == [
        "Negro",
        "Natural",
        "Blanco",
        "Azul Marino",
        "Gris",
        "Beige",
        "Marengo",
    ]
    # Sin skuId en el link, el actual también se devuelve con el suyo: queda fijo.
    assert vs[0].selected and vs[0].url == f"{CORTINA}?skuId=768451"
    assert vs[0].label == "Negro: $11.990"
    assert [v.selected for v in vs[1:]] == [False] * 6
    for v in vs:
        assert v.url == f"{CORTINA}?skuId={v.variant_id}"
        assert v.external_id == CORTINA_SLUG
        assert easy.normalize(v.url) == ProductRef(CORTINA_SLUG, v.url, v.variant_id)


def test_colores_con_precio_y_stock_distintos():
    vs = variants("silla_petra_colores_mixtos.json", f"{PETRA}?skuId=1751149")
    assert vs[0].selected and vs[0].label == "Gris: $84.999 (agotada)"
    assert vs[0].url == f"{PETRA}?skuId=1751149"
    assert {v.label for v in vs[1:]} == {
        "Celeste: $74.799",
        "Marengo: $84.999 (agotada)",
        "Morado Oscuro: $84.999 (agotada)",
        "Beige Oscuro: $74.799",
    }
    gris = parse("silla_petra_colores_mixtos.json", f"{PETRA}?skuId=1751149")
    assert (gris.title, gris.price, gris.list_price, gris.available) == (
        "Silla de Comer Petra (Gris)",
        84999,
        None,
        False,
    )
    celeste = parse("silla_petra_colores_mixtos.json", f"{PETRA}?skuId=1751140")
    assert (celeste.price, celeste.list_price, celeste.available) == (74799, 84999, True)


def test_color_repetido_se_distingue_por_sku():
    vs = variants("silla_bilbao_color_repetido.json", BILBAO)
    assert [v.label for v in vs] == [
        "Gris, SKU 1708676: $79.999",
        "Beige Oscuro: $79.999",
        "Gris, SKU 1708699: $79.999",
    ]
    r = parse("silla_bilbao_color_repetido.json", f"{BILBAO}?skuId=1708699")
    assert r.title == "Silla de Comer Bilbao (Gris, SKU 1708699)"


def test_item_sin_color_usa_otras_variaciones_o_el_sku():
    assert easy.item_label({"variations": ["Tallas"], "Tallas": ["Talla Única"]}) == ""
    assert easy.item_label({"variations": ["Tallas"], "Tallas": ["2 m"]}) == "2 m"
    assert easy.item_label({"variations": ["Tallas", "Color"], "Color": ["Rojo"]}) == "Rojo"
    data = json.loads(fixture_text("easy", "silla_bilbao_color_repetido.json"))
    for it in data[0]["items"]:
        it.pop("Color")
    vs = easy.parse_variants(json.dumps(data), easy.normalize(BILBAO))
    assert vs[0].label == "SKU 1708676: $79.999"


def test_color_que_ya_no_existe():
    with pytest.raises(NotFoundError):
        parse("cortina_7_colores.json", f"{CORTINA}?skuId=123")


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json", CORTINA)


def test_agotado_con_precio_0_no_es_anomalia():
    data = json.loads(fixture_text("easy", "chipeador_agotado.json"))
    data[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 0.0
    r = easy.parse(json.dumps(data), easy.normalize(CORTINA))
    assert (r.price, r.available) == (None, False)
    reading = Reading(price=None, list_price=None, available=False)
    assert check_anomaly(reading, 13500, easy.anomaly_drop_pct, easy.sold_out_without_price) is None


def test_oferta_incompleta_es_error_de_lectura():
    data = json.loads(fixture_text("easy", "cortina_7_colores.json"))
    data[0]["items"][2]["sellers"] = []
    with pytest.raises(FetchError):
        easy.parse(json.dumps(data), easy.normalize(f"{CORTINA}?skuId=768558"))
    # En el selector, el color roto sale sin precio en vez de romper la lista.
    vs = easy.parse_variants(json.dumps(data), easy.normalize(CORTINA))
    assert next(v for v in vs if v.variant_id == "768558").label == "Blanco (agotada)"


@pytest.mark.parametrize(
    ("url", "sku"),
    [
        (CORTINA, ""),
        (f"https://easy.cl/{CORTINA_SLUG}/p", ""),
        (f"http://www.easy.cl/{CORTINA_SLUG}/p/", ""),
        (f"https://WWW.EASY.CL/{CORTINA_SLUG.upper()}/p?utm_source=x#top", ""),
        (f"{CORTINA}?skuId=768558", "768558"),
        (f"{CORTINA}?utm_source=x&skuId=768558#dimensiones", "768558"),
        (f"{CORTINA}?skuId=abc", ""),
    ],
)
def test_normaliza_url(url, sku):
    ref = easy.normalize(url)
    assert ref.external_id == CORTINA_SLUG
    assert ref.variant_id == sku
    assert ref.canonical_url == CORTINA + (f"?skuId={sku}" if sku else "")


def test_matchea_solo_fichas_de_su_dominio():
    assert easy.domain() == "easycl.vtexcommercestable.com.br"
    assert find_processor(CORTINA).name == "easy"
    assert not easy.matches("https://www.easy.cl/")
    assert not easy.matches("https://www.easy.cl/terminaciones/cortinas")
    assert not easy.matches("https://www.easy.cl/busqueda?ft=cortina")
    assert not easy.matches("https://www.easy.cl.evil.com/cortina-x-mkss3ko1gy/p")
    assert not easy.matches("https://wwweasy.cl/cortina-x-mkss3ko1gy/p")
