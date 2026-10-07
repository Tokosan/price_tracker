import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import sfcc as sfcc_mod
from tracker.processors.tricot import TricotProcessor

tricot = TricotProcessor()
POLERON = "https://www.tricot.cl/poleron-mujer-clasico-costuras-683951.html"
CANONICO = "https://www.tricot.cl/683951.html"
XL = POLERON + "?dwvar_683951_color=41&dwvar_683951_size=106&quantity=1"
XS_VARIANTE = "https://www.tricot.cl/poleron-mujer-clasico-costuras-719657383.html"


def parse(fixture, url):
    return tricot.parse(fixture_text("tricot", fixture), tricot.normalize(url))


def variants(fixture, url):
    return tricot.parse_variants(fixture_text("tricot", fixture), tricot.normalize(url))


def test_maestro_sin_talla_con_descuento():
    r = parse("maestro_sin_talla_descuento.json", POLERON)
    # La ficha: "Precio Internet" $6.990, tachado $27.990. `price.list` viene vacío.
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polerón mujer clásico costuras",
        6990,
        27990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.tricot.cl/dw/image/")


def test_talla_agotada():
    r = parse("talla_agotada.json", XL)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polerón mujer clásico costuras (Talla: XL)",
        6990,
        27990,
        False,
    )


def test_pid_de_una_talla_en_stock():
    r = parse("variante_en_stock.json", XS_VARIANTE)
    assert (r.title, r.price, r.available) == (
        "Polerón mujer clásico costuras (Talla: XS)",
        6990,
        True,
    )


def test_sin_pricebook_usa_sales_y_list():
    data = json.loads(fixture_text("tricot", "maestro_sin_talla_descuento.json"))
    data["product"]["pricebookPrices"] = None
    data["product"]["price"]["list"] = {"value": 9990, "currency": "CLP"}
    r = tricot.parse(json.dumps(data), tricot.normalize(POLERON))
    assert (r.price, r.list_price) == (6990, 9990)


def test_sin_descuento_no_hay_list_price():
    data = json.loads(fixture_text("tricot", "maestro_sin_talla_descuento.json"))
    data["product"]["pricebookPrices"]["normalPrice"]["value"] = 6990
    r = tricot.parse(json.dumps(data), tricot.normalize(POLERON))
    assert (r.price, r.list_price) == (6990, None)


@pytest.mark.parametrize("raw", ["<html>error</html>", "{}", '{"product": null}', "[]"])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        tricot.parse(raw, tricot.normalize(POLERON))


def test_seleccion_que_no_existe_es_error_de_lectura():
    raw = fixture_text("tricot", "talla_agotada.json")
    with pytest.raises(FetchError, match="ya no existe"):
        tricot.parse(raw, tricot.normalize(POLERON + "?dwvar_683951_size=999"))


def test_variantes_desde_el_maestro_sin_talla():
    vs = variants("maestro_sin_talla_descuento.json", POLERON)
    assert [(v.label, v.selected) for v in vs] == [
        ("Cualquier talla", True),
        ("Talla: XS", False),
        ("Talla: S", False),
        ("Talla: M", False),
        ("Talla: L", False),
        ("Talla: XL (no disponible)", False),
    ]
    assert vs[0].url == CANONICO and vs[0].variant_id == ""
    assert vs[1].url == CANONICO + "?dwvar_683951_color=41&dwvar_683951_size=101"
    # Cada link del selector se normaliza a la misma variante.
    for v in vs:
        ref = tricot.normalize(v.url)
        assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
            v.external_id,
            v.variant_id,
            v.url,
        )


def test_variantes_desde_una_talla():
    vs = variants("variante_en_stock.json", XS_VARIANTE)
    assert vs[0].selected and vs[0].label == "Talla: XS"
    assert vs[0].external_id == "719657383"
    assert [v.label for v in vs[1:]] == [
        "Talla: S",
        "Talla: M",
        "Talla: L",
        "Talla: XL (no disponible)",
    ]
    assert {v.external_id for v in vs[1:]} == {"683951"}

    vs = variants("talla_agotada.json", XL)
    assert vs[0].selected and vs[0].label == "Talla: XL (no disponible)"
    assert vs[0].variant_id == "color=41&size=106"


@pytest.mark.parametrize(
    "url",
    [
        POLERON,
        CANONICO,
        "http://tricot.cl/poleron-mujer-clasico-costuras-683951.html",
        "https://WWW.TRICOT.CL/Poleron-Mujer-Clasico-Costuras-683951.html?utm_source=x#top",
        POLERON + "?dwvar_683951_size=",  # selección vacía
        POLERON + "?dwvar_123_size=101",  # selección de otro producto
    ],
)
def test_normaliza_url(url):
    ref = tricot.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == ("683951", "", CANONICO)


def test_normaliza_la_seleccion():
    ref = tricot.normalize(XL)
    assert ref.variant_id == "color=41&size=106"
    assert ref.canonical_url == CANONICO + "?dwvar_683951_color=41&dwvar_683951_size=106"
    assert tricot.normalize(ref.canonical_url) == ref
    assert tricot.variation_params(ref) == {
        "pid": "683951",
        "dwvar_683951_color": "41",
        "dwvar_683951_size": "106",
    }
    assert tricot.variant_label(ref.external_id, ref.variant_id) == ""  # va en el título


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(POLERON).name == "tricot"
    assert find_processor(XS_VARIANTE).name == "tricot"
    assert not tricot.matches("https://www.tricot.cl/")
    assert not tricot.matches("https://www.tricot.cl/mujer/polerones")
    assert not tricot.matches("https://www.tricot.cl/search?q=poleron")
    assert not tricot.matches("https://www.tricot.cl/poleron-mujer.html")
    assert not tricot.matches("https://www.tricot.cl/mujer/poleron-683951.html")
    assert not tricot.matches(
        "https://www.tricot.cl/on/demandware.store/Sites-TRICOT_CL-Site/default/"
        "Product-Variation?pid=683951"
    )
    assert not tricot.matches("https://www.tricot.cl.evil.com/poleron-683951.html")
    assert not tricot.matches("https://eviltricot.cl/poleron-683951.html")
    with pytest.raises(ValueError):
        tricot.normalize("https://www.tricot.cl/mujer")


API = "https://www.tricot.cl/on/demandware.store/Sites-TRICOT_CL-Site/default/Product-Variation"


@pytest.fixture
def fake_get(monkeypatch):
    calls = []

    def install(responses):
        async def get_text(url, *, params=None, timeout=30):
            calls.append((url, params))
            result = responses[url]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(sfcc_mod, "get_text", get_text)
        return calls

    return install


async def test_fetch_pide_product_variation(fake_get):
    calls = fake_get({API: fixture_text("tricot", "talla_agotada.json")})
    ref = tricot.normalize(XL)
    assert (await tricot.fetch(ref)).available is False
    assert calls == [(API, tricot.variation_params(ref))]


async def test_inexistente_500_en_api_y_404_en_la_ficha(fake_get):
    url = "https://www.tricot.cl/999999123.html"
    calls = fake_get({API: FetchError("HTTP 500"), url: NotFoundError(f"404 en {url}")})
    with pytest.raises(NotFoundError):
        await tricot.fetch_raw(tricot.normalize(url))
    assert [c[0] for c in calls] == [API, url]
