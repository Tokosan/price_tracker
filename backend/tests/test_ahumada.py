import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.ahumada import AhumadaProcessor, pdp_summary

ahumada = AhumadaProcessor()
HOST = "https://www.farmaciasahumada.cl"
ISDIN = f"{HOST}/protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html"
REFLEXAN = f"{HOST}/reflexan-10-mg-x-20-comprimidos-recubiertos-6.html"
TETINA = f"{HOST}/tetina-pigeon-repuesto-boca-standard-talla-m-2-un-89871.html"


def parse(fixture, url):
    return ahumada.parse(fixture_text("ahumada", fixture), ahumada.normalize(url))


def _con(fixture, cambio):
    data = json.loads(fixture_text("ahumada", fixture))
    cambio(data)
    return json.dumps(data)


def test_descuento_trae_el_precio_normal():
    r = parse("isdin_descuento.json", ISDIN)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Protector Solar Isdin Fusion Water Magic FPS 50 50 mL",
        13859,
        23099,
        "CLP",
        True,
    )
    assert isinstance(r.price, int) and isinstance(r.list_price, int)
    assert r.image_url.startswith(f"{HOST}/dw/image/")


def test_en_stock_sin_descuento():
    r = parse("reflexan_en_stock.json", REFLEXAN)
    assert r.title == "Reflexan 10 mg x 20 Comprimidos Recubiertos"
    assert (r.price, r.list_price, r.available) == (13719, None, True)


def test_agotado_sale_del_boton_de_la_ficha():
    # Product-Variation dice "In Stock" igual; la ficha muestra "Producto sin stock".
    raw = fixture_text("ahumada", "tetina_agotado.json")
    product = json.loads(raw)["variation"]["product"]
    assert product["available"] is True
    assert product["availability"]["messages"] == ["In Stock"]
    r = ahumada.parse(raw, ahumada.normalize(TETINA))
    assert (r.price, r.list_price, r.available) == (7799, None, False)


def test_ignora_el_precio_familia_ahumada():
    def club(data):
        price = data["variation"]["product"]["price"]
        price["hasFamiliaAhumadaPrice"] = True
        price["familiaAhumadaPriceForCart"] = {"value": 9999}

    r = ahumada.parse(_con("isdin_descuento.json", club), ahumada.normalize(ISDIN))
    assert (r.price, r.list_price) == (13859, 23099)


def test_precio_0_no_es_precio():
    def cero(data):
        data["variation"]["product"]["price"]["sales"]["value"] = 0

    r = ahumada.parse(_con("reflexan_en_stock.json", cero), ahumada.normalize(REFLEXAN))
    assert r.price is None


def test_no_es_ficha_de_producto():
    def contenido(data):
        data["pdp"] = {"action": "Page-Show", "add_to_cart": None}

    with pytest.raises(NotFoundError):
        ahumada.parse(_con("reflexan_en_stock.json", contenido), ahumada.normalize(REFLEXAN))


@pytest.mark.parametrize(
    "cambio",
    [
        lambda d: d["pdp"].update(add_to_cart=None),
        lambda d: d["pdp"].update(add_to_cart='<button class="add-to-cart" data-pid="6">'),
        lambda d: d.pop("pdp"),
        lambda d: d.update(variation={"error": "x"}),
        lambda d: d["variation"]["product"].update(id="7"),
    ],
    ids=["sin-boton", "boton-sin-stock", "sin-pdp", "sin-producto", "otro-producto"],
)
def test_respuesta_incompleta_es_error_de_lectura(cambio):
    with pytest.raises(FetchError):
        ahumada.parse(_con("reflexan_en_stock.json", cambio), ahumada.normalize(REFLEXAN))


def test_respuesta_que_no_es_json():
    with pytest.raises(FetchError):
        ahumada.parse("<html>error</html>", ahumada.normalize(REFLEXAN))


def test_pdp_summary_toma_el_boton_del_producto_y_no_los_de_carruseles():
    html = (
        '<div class="page" data-action="Product-Show" data-querystring="pid=6" >'
        '<button class="btn product-tile-add-to-cart" data-pid="7" data-is-unavailable="false">'
        '<button class="add-to-cart-global btn" data-pid="6">'
        '<button class="add-to-cart btn btn-primary"\n data-pid="6"\n'
        ' data-is-unavailable="true"\n disabled>'
    )
    summary = pdp_summary(html, "6")
    assert summary["action"] == "Product-Show"
    assert 'data-is-unavailable="true"' in summary["add_to_cart"]
    assert pdp_summary(html, "60")["add_to_cart"] is None
    assert pdp_summary("<html></html>", "6") == {"action": None, "add_to_cart": None}


def test_sin_variantes():
    assert ahumada.supports_variants is False
    raw = fixture_text("ahumada", "isdin_descuento.json")
    assert ahumada.parse_variants(raw, ahumada.normalize(ISDIN)) == []


@pytest.mark.parametrize(
    "url",
    [
        ISDIN,
        "https://farmaciasahumada.cl/protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html",
        "http://www.farmaciasahumada.cl/Protector-Solar-Isdin-Fusion-Water-Magic-FPS-50-50-mL-92197.html",
        f"{ISDIN}?quantity=1&dwvar_92197_x=y#tab",
    ],
)
def test_normaliza_url(url):
    assert ahumada.normalize(url) == ProductRef("92197", ISDIN)


def test_pid_corto_y_slug_con_parentesis():
    assert ahumada.normalize(REFLEXAN) == ProductRef("6", REFLEXAN)
    pampers = f"{HOST}/panal-pampers-proteccion-insuperable-talla-m-%286-10-kg%29-62-un-97257.html"
    assert ahumada.normalize(pampers) == ProductRef("97257", pampers)


def test_pide_product_variation_de_su_sitio():
    assert ahumada.controller_url("Product-Variation") == (
        f"{HOST}/on/demandware.store/Sites-ahumada-cl-Site/default/Product-Variation"
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(ISDIN).name == "ahumada"
    assert not ahumada.matches(f"{HOST}/")
    assert not ahumada.matches(f"{HOST}/belleza/proteccion-solar/rostro")
    assert not ahumada.matches(f"{HOST}/search?q=protector")
    assert not ahumada.matches(f"{HOST}/belleza/protector-solar-92197.html")  # dos segmentos
    assert not ahumada.matches(f"{HOST}/protector-solar.html")  # sin pid
    assert not ahumada.matches("https://www.farmaciasahumada.cl.evil.com/protector-92197.html")
    assert not ahumada.matches("https://evilfarmaciasahumada.cl/protector-92197.html")
    assert not ahumada.matches("https://www.hites.com/protector-solar-92197001.html")
    assert not ahumada.matches("ftp://www.farmaciasahumada.cl/protector-92197.html")
