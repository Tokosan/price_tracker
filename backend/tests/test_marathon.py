import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import marathon as marathon_mod
from tracker.processors import sfcc as sfcc_mod
from tracker.processors.marathon import MarathonProcessor

marathon = MarathonProcessor()
PUMA = (
    "https://www.marathon.cl/marcas/puma/puma-zapatillas-magmax-nitro-2/312126-03/11140411010.html"
)
CHAQUETA_S = (
    "https://www.marathon.cl/jack_wolfskin/jack-wolfskin-chaqueta-elsberg/1115881-1010/"
    "10980728002.html"
)
CHAQUETA_M = "https://www.marathon.cl/10980728003.html"
API = "https://www.marathon.cl/on/demandware.store/Sites-MarathonChile-Site/es_CL/Product-Variation"


def parse(fixture, url):
    return marathon.parse(fixture_text("marathon", fixture), marathon.normalize(url))


def test_en_stock_con_descuento():
    r = parse("zapatilla_en_stock_descuento.json", PUMA)
    # La ficha: $111.993, tachado $159.990 (el -10 % con Banco de Chile no se guarda).
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Puma Zapatillas MagMax NITRO 2 (Talla: 5.5)",
        111993,
        159990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.marathon.cl/dw/image/")


def test_talla_agotada():
    r = parse("chaqueta_talla_agotada.json", CHAQUETA_M)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Jack Wolfskin Chaqueta Elsberg (Talla: M)",
        75996,
        189990,
        False,
    )


def test_ignora_la_promocion_del_banco():
    raw = fixture_text("marathon", "chaqueta_talla_en_stock.json")
    promo = json.loads(raw)["product"]["applicableBankPromotion"]
    assert promo["newPriceFormatted"] == "$ 68.396"
    r = marathon.parse(raw, marathon.normalize(CHAQUETA_S))
    assert (r.price, r.list_price, r.available) == (75996, 189990, True)


@pytest.mark.parametrize("raw", ["<html>error</html>", "{}", '{"product": null}'])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        marathon.parse(raw, marathon.normalize(PUMA))


@pytest.mark.parametrize(
    "url",
    [
        PUMA,
        "https://www.marathon.cl/11140411010.html",
        "http://marathon.cl/otra/ruta/11140411010.html?utm_source=x&quantity=2#top",
        "https://WWW.MARATHON.CL/Marcas/Puma/x/312126-03/11140411010.html",
    ],
)
def test_normaliza_url(url):
    ref = marathon.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "11140411010",
        "",
        "https://www.marathon.cl/11140411010.html",
    )


def test_pide_product_variation_con_image_size():
    # Sin `imageSize` la tienda responde HTTP 500 a todo.
    assert marathon.variation_params(marathon.normalize(PUMA)) == {
        "pid": "11140411010",
        "imageSize": "hi-res",
    }


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(PUMA).name == "marathon"
    assert find_processor(CHAQUETA_S).name == "marathon"
    assert not marathon.matches("https://www.marathon.cl/")
    assert not marathon.matches("https://www.marathon.cl/deporte/outdoor")
    assert not marathon.matches("https://www.marathon.cl/marcas/puma")
    assert not marathon.matches("https://www.marathon.cl/hoka/hoka-zapatillas-bondi-9.html")
    assert not marathon.matches(
        "https://www.marathon.cl/on/demandware.store/Sites-MarathonChile-Site/es_CL/"
        "Product-Variation?pid=11140411010"
    )
    assert not marathon.matches("https://www.marathon.cl.evil.com/x/11140411010.html")
    assert not marathon.matches("https://evilmarathon.cl/x/11140411010.html")
    with pytest.raises(ValueError):
        marathon.normalize("https://www.marathon.cl/hoka")


def test_el_parseo_puro_no_trae_variantes():
    raw = fixture_text("marathon", "chaqueta_talla_en_stock.json")
    assert marathon.parse_variants(raw, marathon.normalize(CHAQUETA_S)) == []


@pytest.fixture
def fake_get(monkeypatch):
    """`get_text` falso: la respuesta depende de la talla pedida (o de la URL)."""
    calls = []
    monkeypatch.setattr(marathon_mod, "SIZE_PAUSE_S", 0)

    def install(by_size, page=None):
        async def get_text(url, *, params=None, timeout=30):
            calls.append((url, params))
            if url != API:
                result = page
            else:
                size = next((v for k, v in (params or {}).items() if k.endswith("_size")), None)
                result = by_size[size]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(sfcc_mod, "get_text", get_text)
        return calls

    return install


async def test_inspect_pide_cada_talla(fake_get):
    calls = fake_get(
        {
            None: fixture_text("marathon", "chaqueta_talla_en_stock.json"),
            "M": fixture_text("marathon", "chaqueta_talla_agotada.json"),
            "L": FetchError("HTTP 500"),  # una talla que falla no rompe el selector
            "XL": fixture_text("marathon", "chaqueta_talla_agotada.json"),  # no es XL: fuera
        }
    )
    ins = await marathon.inspect(marathon.normalize(CHAQUETA_S))
    assert ins.result.available is True
    assert [(v.external_id, v.label, v.url, v.selected) for v in ins.variants] == [
        ("10980728002", "Talla: S", "https://www.marathon.cl/10980728002.html", True),
        ("10980728003", "Talla: M (no disponible)", CHAQUETA_M, False),
    ]
    # Cada talla se pide al maestro con el color y la talla.
    assert calls[1] == (
        API,
        {
            "pid": "M0441115881-1010",
            "dwvar_M0441115881-1010_color": "1115881-1010",
            "dwvar_M0441115881-1010_size": "M",
            "imageSize": "hi-res",
        },
    )
    assert len(calls) == 4
    for v in ins.variants:
        assert marathon.normalize(v.url).external_id == v.external_id


async def test_maestro_con_espacios_y_tallas_que_no_existen(fake_get):
    # La curva del maestro va de 1 a 10.5, pero el modelo solo tiene 5.5 a 9 (las otras
    # vienen sin `eanValue`): solo se piden esas. El pid del maestro lleva un espacio.
    other = fixture_text("marathon", "chaqueta_talla_agotada.json")
    sizes = ["6", "6.5", "7", "7.5", "8", "8.5", "9"]
    calls = fake_get(
        {None: fixture_text("marathon", "zapatilla_en_stock_descuento.json")}
        | dict.fromkeys(sizes, other)
    )
    ins = await marathon.inspect(marathon.normalize(PUMA))
    assert [c[1].get("dwvar_M003312126 03_size") for c in calls[1:]] == sizes
    assert {c[1]["pid"] for c in calls[1:]} == {"M003312126 03"}
    assert ins.variants == []  # ninguna respuesta coincidió con la talla pedida


async def test_inexistente_500_en_api_y_404_en_la_ficha(fake_get):
    url = "https://www.marathon.cl/99999999123.html"
    calls = fake_get({None: FetchError("HTTP 500")}, page=NotFoundError(f"404 en {url}"))
    with pytest.raises(NotFoundError):
        await marathon.fetch_raw(marathon.normalize(url))
    assert [c[0] for c in calls] == [API, url]
