import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.drsimi import DrSimiProcessor

drsimi = DrSimiProcessor()
PARACETAMOL = "https://www.drsimi.cl/paracetamol-500-mg-16-comprimidos/p"
BISOLVON = "https://www.drsimi.cl/bisolvon-adultos-bromhexina-clorhidrato-8mg-5ml-jarabe-125ml/p"
ROSUVASTATINA = "https://www.drsimi.cl/rosuvastatina-20mg-30comp-rec-be0280-1/p"
POWER_GEL = (
    "https://www.drsimi.cl/power-gel-con-cafeina-aminoacidos-sabor-cafe-gel-sachet-35gr-ch6177-1/p"
)


def parse(fixture, url=PARACETAMOL):
    return drsimi.parse(fixture_text("drsimi", fixture), drsimi.normalize(url))


def _offer(data):
    return data[0]["items"][0]["sellers"][0]["commertialOffer"]


def test_en_stock():
    r = parse("paracetamol_en_stock.json")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Paracetamol 500 mg 16 comprimidos",
        480,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://farmaciasdeldrsimicl.vteximg.com.br/")


def test_agotado_conserva_el_precio():
    raw = fixture_text("drsimi", "bisolvon_agotado.json")
    offer = _offer(json.loads(raw))
    assert (offer["IsAvailable"], offer["AvailableQuantity"]) == (False, 0)
    r = drsimi.parse(raw, drsimi.normalize(BISOLVON))
    assert r.title == "Bisolvon adulto bromhexina 8 mg/5 mL jarabe 125 mL"
    assert (r.price, r.list_price, r.available) == (5400, None, False)


@pytest.mark.parametrize(
    ("fixture", "url", "teaser", "price"),
    [
        (
            "rosuvastatina_club_de_amigos.json",
            ROSUVASTATINA,
            "Club de amigos - 33% de descuento al llevar 3",
            6400,
        ),
        ("power_gel_3x2.json", POWER_GEL, "Promoción 3x2 Xgear Cafeina", 1800),
    ],
)
def test_promociones_por_cantidad_no_cambian_el_precio(fixture, url, teaser, price):
    raw = fixture_text("drsimi", fixture)
    offer = _offer(json.loads(raw))
    assert [t["Name"] for t in offer["PromotionTeasers"]] == [teaser]
    r = drsimi.parse(raw, drsimi.normalize(url))
    assert (r.price, r.list_price, r.available) == (price, None, True)


def test_promocion_del_catalogo_usa_price_without_discount():
    # Dr. Simi no usa ListPrice: una promoción deja el precio previo en PriceWithoutDiscount.
    data = json.loads(fixture_text("drsimi", "paracetamol_en_stock.json"))
    _offer(data).update(Price=360.0, ListPrice=360.0, PriceWithoutDiscount=480.0)
    r = drsimi.parse(json.dumps(data), drsimi.normalize(PARACETAMOL))
    assert (r.price, r.list_price) == (360, 480)


def test_list_price_tiene_prioridad():
    data = json.loads(fixture_text("drsimi", "paracetamol_en_stock.json"))
    _offer(data).update(Price=360.0, ListPrice=600.0, PriceWithoutDiscount=480.0)
    r = drsimi.parse(json.dumps(data), drsimi.normalize(PARACETAMOL))
    assert (r.price, r.list_price) == (360, 600)


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json")


def test_respuesta_rara_es_error_de_lectura():
    with pytest.raises(FetchError):
        drsimi.parse("<html>error</html>", drsimi.normalize(PARACETAMOL))


def test_sin_variantes():
    assert drsimi.supports_variants is False
    assert (
        drsimi.parse_variants(
            fixture_text("drsimi", "paracetamol_en_stock.json"), drsimi.normalize(PARACETAMOL)
        )
        == []
    )


@pytest.mark.parametrize(
    "url",
    [
        PARACETAMOL,
        "https://drsimi.cl/paracetamol-500-mg-16-comprimidos/p",
        "http://www.drsimi.cl/paracetamol-500-mg-16-comprimidos/p/",
        "https://WWW.DRSIMI.CL/Paracetamol-500-MG-16-Comprimidos/p?skuId=1#x",
    ],
)
def test_normaliza_url(url):
    ref = drsimi.normalize(url)
    assert ref == ProductRef("paracetamol-500-mg-16-comprimidos", PARACETAMOL)


def test_pide_la_api_de_su_cuenta():
    assert drsimi.search_url("paracetamol-500-mg-16-comprimidos") == (
        "https://farmaciasdeldrsimicl.vtexcommercestable.com.br/api/catalog_system/pub/"
        "products/search/paracetamol-500-mg-16-comprimidos/p"
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(PARACETAMOL).name == "drsimi"
    assert find_processor(ROSUVASTATINA).name == "drsimi"
    assert not drsimi.matches("https://www.drsimi.cl/")
    assert not drsimi.matches("https://www.drsimi.cl/medicamentos")
    assert not drsimi.matches("https://www.drsimi.cl/medicamentos/analgesicos/p")
    assert not drsimi.matches("https://www.drsimi.cl/ofertas/s?map=ft")
    assert not drsimi.matches("https://www.drsimi.cl/229?map=productClusterIds")
    assert not drsimi.matches("https://www.drsimi.cl.evil.com/paracetamol-500-mg/p")
    assert not drsimi.matches("https://evildrsimi.cl/paracetamol-500-mg/p")
