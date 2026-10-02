import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.contrapunto import ContrapuntoProcessor
from tracker.rules import Reading, check_anomaly

cp = ContrapuntoProcessor()
BASE = "https://contrapunto.cl/products"
VERITY = f"{BASE}/verity"


def parse(fixture, url):
    return cp.parse(fixture_text("contrapunto", fixture), cp.normalize(url))


def test_descuento_permanente():
    # La ficha muestra $15,210 y tachado $16,900 (-10 %); el JSON, 1521000 y 1690000.
    r = parse("descuento.json", VERITY)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Verity",
        15210,
        16900,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://cdn.shopify.com/")


def test_sin_descuento():
    r = parse("sin_descuento.json", f"{BASE}/sed-de-vino")
    assert (r.title, r.price, r.list_price, r.available) == ("Sed de vino", 19900, None, True)


def test_agotado():
    r = parse("agotado.json", f"{BASE}/el-conde-de-montecristo-1")
    assert (r.title, r.price, r.list_price, r.available) == (
        "El conde de Montecristo",
        16000,
        20000,
        False,
    )


def test_preventa_se_puede_comprar():
    r = parse("preventa.json", f"{BASE}/ill-believe-in-anything")
    assert r.title == "[PREVENTA] I'll believe in anything"
    assert (r.price, r.list_price, r.available) == (25110, 27900, True)


def test_agotado_con_precio_0_no_es_anomalia():
    r = parse("agotado_precio_0.json", f"{BASE}/el-molino-y-la-sangre")
    assert (r.price, r.list_price, r.available) == (None, None, False)
    reading = Reading(price=None, list_price=None, available=False)
    assert check_anomaly(reading, 15000, cp.anomaly_drop_pct, cp.sold_out_without_price) is None


def test_sin_selector_de_variantes():
    # Los libros tienen una sola variante: `?variant=` se ignora.
    assert (
        cp.parse_variants(fixture_text("contrapunto", "descuento.json"), cp.normalize(VERITY)) == []
    )
    ref = cp.normalize(f"{VERITY}?variant=43053451608139")
    assert (ref.variant_id, ref.canonical_url) == ("", VERITY)


@pytest.mark.parametrize(
    "url",
    [
        VERITY,
        "https://www.contrapunto.cl/products/verity",
        "http://contrapunto.cl/products/verity/",
        "https://contrapunto.cl/products/VERITY?utm_source=x#top",
        "https://contrapunto.cl/collections/novedades/products/verity",
    ],
)
def test_normaliza_url(url):
    ref = cp.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == ("verity", VERITY, "")


def test_matchea_solo_fichas_de_su_dominio():
    assert cp.domain() == "contrapunto.cl"
    assert find_processor(VERITY).name == "contrapunto"
    assert not cp.matches("https://contrapunto.cl/")
    assert not cp.matches("https://contrapunto.cl/collections/novedades")
    assert not cp.matches("https://contrapunto.cl/collections/colleen-hoover")
    assert not cp.matches("https://contrapunto.cl/search?q=verity")
    assert not cp.matches("https://contrapunto.cl/pages/tiendas")
    assert not cp.matches("https://contrapunto.cl.evil.com/products/verity")
    assert not cp.matches("https://notcontrapunto.cl/products/verity")
