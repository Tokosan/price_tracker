import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor, vtex
from tracker.processors.jumbo import JumboProcessor
from tracker.processors.santaisabel import SantaIsabelProcessor
from tracker.rules import Reading, check_anomaly

si = SantaIsabelProcessor()
ATUN = "https://www.santaisabel.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p"
ARROZ = "https://www.santaisabel.cl/arroz-basmati-miraflores-400g-1871480/p"


def parse(fixture, url=ATUN):
    return si.parse(fixture_text("santaisabel", fixture), si.normalize(url))


def test_en_stock():
    r = parse("atun_en_stock.json")
    assert (r.title, r.price, r.currency, r.available) == (
        "Atún Lomitos en Agua 91 g drenado, 140 g neto",
        1950,
        "CLP",
        True,
    )
    assert r.list_price is None
    assert r.image_url.startswith("https://santaisabel.vteximg.com.br/")


def test_descuento_trae_precio_antes():
    url = "https://www.santaisabel.cl/atun-antartic-lomitos-en-agua-91-g-drenado-1989506/p"
    r = parse("antartic_descuento.json", url)
    assert (r.price, r.list_price, r.available) == (1000, 1200, True)


def test_agotado_con_precio_0_no_es_anomalia():
    url = "https://www.santaisabel.cl/whisky-ballantines-10a-750cc-40-2028463/p"
    r = parse("whisky_agotado_precio_0.json", url)
    assert r.title == "Whisky Ballantine's 10 Años 40° 750 cc"
    assert (r.price, r.list_price, r.available) == (None, None, False)
    reading = Reading(price=None, list_price=None, available=False)
    assert check_anomaly(reading, 15000, si.anomaly_drop_pct, si.sold_out_without_price) is None


def test_slug_de_jumbo_se_lee_por_refid():
    # El slug no existe en Santa Isabel; la fixture es la respuesta de alternateIds_RefId.
    r = parse("arroz_slug_de_jumbo.json", ARROZ)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Arroz Basmati Miraflores 400 g",
        2990,
        None,
        True,
    )


def test_respaldo_no_acepta_otro_producto():
    data = json.loads(fixture_text("santaisabel", "arroz_slug_de_jumbo.json"))
    data[0]["productReference"] = "1234567"
    data[0]["items"][0]["referenceId"] = [{"Key": "RefId", "Value": "1234567"}]
    with pytest.raises(NotFoundError):
        si.parse(json.dumps(data), si.normalize(ARROZ))


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json")


def test_oferta_incompleta_es_error_de_lectura():
    data = json.loads(fixture_text("santaisabel", "atun_en_stock.json"))
    data[0]["items"][0]["sellers"] = []
    with pytest.raises(FetchError):
        si.parse(json.dumps(data), si.normalize(ATUN))


def _fake_get_text(monkeypatch, responses):
    calls = []

    async def fake(url, **kwargs):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(vtex, "get_text", fake)
    return calls


async def test_fetch_usa_el_respaldo_si_el_slug_no_existe(monkeypatch):
    calls = _fake_get_text(monkeypatch, ["[]", "[{}]"])
    assert await si.fetch_raw(si.normalize(ARROZ)) == "[{}]"
    assert calls == [
        "https://santaisabel.vtexcommercestable.com.br/api/catalog_system/pub/products/search/"
        "arroz-basmati-miraflores-400g-1871480/p",
        "https://santaisabel.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
        "?fq=alternateIds_RefId:1871480",
    ]


async def test_fetch_no_usa_el_respaldo_si_el_slug_existe(monkeypatch):
    calls = _fake_get_text(monkeypatch, ["[{}]"])
    assert await si.fetch_raw(si.normalize(ATUN)) == "[{}]"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("proc", "url"),
    [
        # Sufijo corto: no es un RefId.
        (si, "https://www.santaisabel.cl/queso-mantecoso-500grs-2/p"),
        (si, "https://www.santaisabel.cl/papel-arroz-alinsa/p"),
        # Jumbo no activa el respaldo.
        (JumboProcessor(), "https://www.jumbo.cl/arroz-basmati-miraflores-400g-1871480/p"),
    ],
)
async def test_sin_respaldo(monkeypatch, proc, url):
    calls = _fake_get_text(monkeypatch, ["[]"])
    with pytest.raises(NotFoundError):
        proc.parse(await proc.fetch_raw(proc.normalize(url)), proc.normalize(url))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        ATUN,
        "https://santaisabel.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p",
        "http://www.santaisabel.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p/",
        "https://WWW.SANTAISABEL.CL/Atun-Robinson-Crusoe-Lomitos-En-Agua-140-G-Neto-2036254/p?sc=1#x",
    ],
)
def test_normaliza_url(url):
    ref = si.normalize(url)
    assert ref == ProductRef("atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254", ATUN)


def test_matchea_solo_fichas_de_su_dominio():
    assert si.domain() == "santaisabel.vtexcommercestable.com.br"
    assert find_processor(ATUN).name == "santaisabel"
    assert find_processor(ATUN.replace("santaisabel", "jumbo")).name == "jumbo"
    assert not si.matches("https://www.santaisabel.cl/")
    assert not si.matches("https://www.santaisabel.cl/despensa/conservas")
    assert not si.matches("https://www.santaisabel.cl/busqueda?ft=atun")
    assert not si.matches("https://www.santaisabel.cl.evil.com/atun-robinson-2036254/p")
    assert not si.matches("https://evilsantaisabel.cl/atun-robinson-2036254/p")
