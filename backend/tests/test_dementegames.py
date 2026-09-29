import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.dementegames import DementeGamesProcessor

dg = DementeGamesProcessor()
GLOOMHAVEN = "https://dementegames.cl/tematicos/189-gloomhaven.html"


def parse(fixture, url):
    return dg.parse(fixture_text("dementegames", fixture), dg.normalize(url))


def test_en_stock():
    r = parse("flip7_en_stock.html", "https://dementegames.cl/familiares/6079-flip-7.html")
    assert (r.title, r.price, r.currency, r.available) == ("Flip 7", 16990, "CLP", True)
    assert r.list_price is None
    assert r.image_url.endswith(".jpg")


def test_agotado_sin_availability_usa_la_cantidad():
    # El data-product de este tema no trae `availability`: cantidad 0 = agotado.
    r = parse("gloomhaven_agotado.html", GLOOMHAVEN)
    assert (r.title, r.price, r.available) == ("Gloomhaven", 129990, False)


def test_oferta_trae_precio_base():
    r = parse("frostpunk_oferta.html", "https://dementegames.cl/cooperativos/2914-frostpunk.html")
    assert (r.price, r.list_price) == (148491, 164990)


def test_preventa_con_stock_esta_disponible():
    url = "https://dementegames.cl/marvel-champions/7037-marvel-champions-iron-fist.html"
    r = parse("ironfist_preventa.html", url)
    assert r.available is True and r.price == 16990


@pytest.mark.parametrize(
    "url",
    [
        GLOOMHAVEN,
        "https://www.dementegames.cl/tematicos/189-gloomhaven.html?utm_source=x",
        "http://dementegames.cl/inicio/189-gloomhaven.html#descripcion",
    ],
)
def test_normaliza_url(url):
    ref = dg.normalize(url)
    assert ref.external_id == "189"
    assert ref.canonical_url.startswith("https://dementegames.cl/")
    assert "?" not in ref.canonical_url and "#" not in ref.canonical_url


def test_el_registro_no_confunde_tiendas_prestashop():
    assert find_processor(GLOOMHAVEN).name == "dementegames"
    assert find_processor("https://www.entrejuegos.cl/avanzados/18597-frosthaven.html").name == (
        "entrejuegos"
    )
    assert not dg.matches("https://dementegames.cl/12-tematicos")
    assert not dg.matches("https://dementegames.cl.evil.com/tematicos/189-gloomhaven.html")
