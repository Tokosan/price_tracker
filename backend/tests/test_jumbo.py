import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.jumbo import JumboProcessor
from tracker.processors.vtex import VtexProcessor
from tracker.rules import Reading, check_anomaly

jumbo = JumboProcessor()
ATUN = "https://www.jumbo.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p"


def parse(fixture, url=ATUN):
    return jumbo.parse(fixture_text("jumbo", fixture), jumbo.normalize(url))


def test_en_stock():
    r = parse(
        "arroz_en_stock.json",
        "https://www.jumbo.cl/arroz-miraflores-1-kg-pregraneado-grado-1-grano-largo/p",
    )
    assert (r.title, r.price, r.currency, r.available) == (
        "Arroz Pregraneado Miraflores 1 kg",
        2730,
        "CLP",
        True,
    )
    assert r.list_price is None  # ListPrice igual a Price
    assert r.image_url.startswith("https://jumbocl.vteximg.com.br/")


def test_descuento_trae_precio_antes():
    r = parse("atun_descuento.json")
    assert r.title == "Atún Lomitos en Agua 91 g drenado, 140 g neto"
    assert (r.price, r.list_price, r.available) == (1490, 2000, True)
    assert isinstance(r.price, int) and isinstance(r.list_price, int)


def test_descuento_queso():
    url = "https://www.jumbo.cl/quesomantecoso-quilque-28laminasenvaseresellablealvacio500grs-2/p"
    r = parse("queso_descuento.json", url)
    assert (r.price, r.list_price, r.available) == (5750, 7090, True)


def test_agotado_con_precio():
    url = "https://www.jumbo.cl/lomos-de-jurel-aceite-san-jose-104-gr-dr-1939060/p"
    r = parse("jurel_agotado.json", url)
    assert r.title == "Lomos de Jurel en Aceite San José 104 g drenado"
    assert (r.price, r.list_price, r.available) == (1530, None, False)


def test_agotado_con_precio_0_no_es_anomalia():
    url = "https://www.jumbo.cl/choclitos-coctel-wasil-225-g-drenado-270576/p"
    r = parse("choclitos_agotado_precio_0.json", url)
    assert r.title == "Choclito Cóctel Wasil en Almíbar 225 g"
    assert (r.price, r.list_price, r.available) == (None, None, False)
    reading = Reading(price=r.price, list_price=None, available=False)
    assert (
        check_anomaly(reading, 2000, jumbo.anomaly_drop_pct, jumbo.sold_out_without_price) is None
    )


def test_precio_0_con_stock_no_se_vuelve_precio():
    data = json.loads(fixture_text("jumbo", "arroz_en_stock.json"))
    offer = data[0]["items"][0]["sellers"][0]["commertialOffer"]
    offer["Price"] = 0.0
    r = jumbo.parse(json.dumps(data), jumbo.normalize(ATUN))
    assert r.price is None and r.available is True
    reading = Reading(price=None, list_price=None, available=True)
    assert check_anomaly(reading, 2730, jumbo.anomaly_drop_pct, jumbo.sold_out_without_price)


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json")


@pytest.mark.parametrize("raw", ["<html>error</html>", '{"error": "x"}'])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        jumbo.parse(raw, jumbo.normalize(ATUN))


def test_sin_variantes():
    assert jumbo.supports_variants is False
    assert (
        jumbo.parse_variants(fixture_text("jumbo", "atun_descuento.json"), jumbo.normalize(ATUN))
        == []
    )


@pytest.mark.parametrize(
    "url",
    [
        ATUN,
        "https://jumbo.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p",
        "http://www.jumbo.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p/",
        "https://WWW.JUMBO.CL/Atun-Robinson-Crusoe-Lomitos-En-Agua-140-G-Neto-2036254/p?sc=11#x",
    ],
)
def test_normaliza_url(url):
    ref = jumbo.normalize(url)
    assert ref == ProductRef("atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254", ATUN)


def test_pide_la_api_de_su_cuenta():
    assert jumbo.domain() == "jumbocl.vtexcommercestable.com.br"
    assert jumbo.search_url("arroz-x-1") == (
        "https://jumbocl.vtexcommercestable.com.br/api/catalog_system/pub/products/search/arroz-x-1/p"
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(ATUN).name == "jumbo"
    assert not jumbo.matches("https://www.jumbo.cl/")
    assert not jumbo.matches("https://www.jumbo.cl/despensa/conservas")
    assert not jumbo.matches("https://www.jumbo.cl/despensa/conservas/p")  # dos segmentos
    assert not jumbo.matches("https://www.jumbo.cl/busqueda?ft=atun")
    assert not jumbo.matches("https://www.jumbo.cl.evil.com/atun-robinson-2036254/p")
    assert not jumbo.matches("https://eviljumbo.cl/atun-robinson-2036254/p")
    assert not jumbo.matches("https://www.santaisabel.cl/atun-robinson-2036254/p")


class _ConColores(VtexProcessor):
    name = "prueba"
    label = "Prueba"
    host = "www.tienda.cl"
    account = "tienda"
    supports_variants = True

    def item_label(self, item):
        return item["Color"][0]


def test_base_con_variantes_elige_el_item():
    data = json.loads(fixture_text("jumbo", "arroz_en_stock.json"))
    rojo = json.loads(json.dumps(data[0]["items"][0]))
    rojo.update(itemId="999", Color=["Rojo"])
    rojo["sellers"][0]["commertialOffer"].update(
        Price=3000.0, IsAvailable=False, AvailableQuantity=0
    )
    data[0]["items"][0]["Color"] = ["Azul"]
    data[0]["items"].append(rojo)
    raw = json.dumps(data)
    proc = _ConColores()
    ref = proc.normalize("https://tienda.cl/arroz/p")

    variants = proc.parse_variants(raw, ref)
    first_id = data[0]["items"][0]["itemId"]
    assert [(v.label, v.variant_id, v.selected) for v in variants] == [
        ("Azul", first_id, True),
        ("Rojo", "999", False),
    ]
    assert all(v.url == "https://www.tienda.cl/arroz/p" for v in variants)

    r = proc.parse(raw, ProductRef(ref.external_id, ref.canonical_url, "999"))
    assert (r.price, r.available) == (3000, False)
    with pytest.raises(NotFoundError):
        proc.parse(raw, ProductRef(ref.external_id, ref.canonical_url, "123"))
