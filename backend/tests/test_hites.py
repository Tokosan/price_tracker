import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import hites as hites_mod
from tracker.processors.hites import HitesProcessor

hites = HitesProcessor()
MARIO = "https://www.hites.com/juego-nintendo-switch-2-mario-kart-world-957877001.html"
BANANO = "https://www.hites.com/banano-hip-pouch-1l-loam-10059000211001.html"
NOTEBOOK = (
    "https://www.hites.com/notebook-gamer-15.6-asus-tuf-gaming-a15-amd-ryzen-7-8-gb-ram-"
    "nvidia-geforce-rtx-3050-512-gb-ssd-967752001.html"
)
POLERA = "https://www.hites.com/polera-basica-lisa-regular-manga-corta-cuello-pique-hombre-herald-954699.html"
POLERA_TL = (
    POLERA + "?dwvar_954699_color=NARANJA&dwvar_954699_Talla-Vestuario-Generica=TL&quantity=1"
)


def parse(fixture, url):
    return hites.parse(fixture_text("hites", fixture), hites.normalize(url))


def variants(fixture, url):
    return hites.parse_variants(fixture_text("hites", fixture), hites.normalize(url))


def test_en_stock():
    r = parse("en_stock_mario_kart.json", MARIO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Juego Nintendo Switch 2 Mario Kart World",
        79990,
        94990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.hites.com/dw/image/")


def test_descuento_de_marketplace():
    r = parse("descuento_marketplace_banano.json", BANANO)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Banano Hip Pouch 1l Loam",
        56290,
        63990,
        True,
    )


def test_ignora_el_precio_con_tarjeta_hites():
    raw = fixture_text("hites", "tarjeta_hites_notebook.json")
    prices = json.loads(raw)["product"]["price"]
    assert prices["hites"]["value"] == prices["bestPrice"]["value"] == 699990
    r = hites.parse(raw, hites.normalize(NOTEBOOK))
    assert (r.price, r.list_price, r.available) == (719990, 1099990, True)


def test_maestro_sin_seleccion_lee_la_variante_por_defecto():
    r = parse("polera_maestro.json", POLERA)
    assert r.title == "Polera Básica Lisa Regular Manga Corta Cuello Piqué Hombre Herald"
    assert (r.price, r.list_price, r.available) == (4990, 16990, True)


def test_combinacion_agotada():
    r = parse("polera_variante_agotada.json", POLERA_TL)
    assert (r.price, r.list_price, r.available) == (4990, 16990, False)
    assert r.image_url is None


def test_disponible_exige_in_stock():
    data = json.loads(fixture_text("hites", "en_stock_mario_kart.json"))
    data["product"]["availability"]["status"] = "NOT_AVAILABLE"
    r = hites.parse(json.dumps(data), hites.normalize(MARIO))
    assert r.available is False


def test_sin_precio_normal_mayor_no_hay_list_price():
    data = json.loads(fixture_text("hites", "en_stock_mario_kart.json"))
    data["product"]["price"]["list"] = None
    r = hites.parse(json.dumps(data), hites.normalize(MARIO))
    assert (r.price, r.list_price) == (79990, None)
    data["product"]["price"]["list"] = {"value": 79990, "currency": "CLP"}
    assert hites.parse(json.dumps(data), hites.normalize(MARIO)).list_price is None


def test_precio_por_rango_no_inventa_precio():
    data = json.loads(fixture_text("hites", "polera_variante_agotada.json"))
    data["product"]["price"] = {"type": "range", "min": {}, "max": {}}
    r = hites.parse(json.dumps(data), hites.normalize(POLERA_TL))
    assert (r.price, r.list_price, r.available) == (None, None, False)


@pytest.mark.parametrize("raw", ["<html>error</html>", "{}", '{"product": null}', "[]"])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        hites.parse(raw, hites.normalize(MARIO))


def test_variantes_desde_una_combinacion():
    vs = variants("polera_variante_agotada.json", POLERA_TL)
    current = vs[0]
    assert current.selected and current.label == "Color: NARANJA, Talla: L (no disponible)"
    assert current.variant_id == "Talla-Vestuario-Generica=TL&color=NARANJA"
    assert current.url == hites.normalize(POLERA_TL).canonical_url
    labels = [v.label for v in vs[1:]]
    assert labels[:5] == [
        "Color: ROSADO, Talla: L",
        "Color: DAMASCO, Talla: L",
        "Color: AMARILLO, Talla: L",
        "Color: MORADO, Talla: L",
        "Color: STONE, Talla: L (no disponible)",
    ]
    assert "Color: NARANJA, Talla: M" in labels
    assert len(vs) == len({(v.external_id, v.variant_id) for v in vs}) == 10
    # Cada link del selector se normaliza a la misma variante.
    for v in vs:
        ref = hites.normalize(v.url)
        assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
            v.external_id,
            v.variant_id,
            v.url,
        )


def test_variantes_desde_un_maestro_sin_seleccion():
    vs = variants("polera_maestro.json", POLERA)
    assert vs[0].selected and vs[0].label == "Color: NARANJA, Talla: M"
    # Se ofrece la combinación explícita, no el maestro (cuya variante por defecto cambia).
    assert vs[0].variant_id == "Talla-Vestuario-Generica=TM&color=NARANJA"
    assert "dwvar_954699_color=NARANJA" in vs[0].url
    assert sum(v.selected for v in vs) == 1


def test_sin_variantes():
    assert variants("descuento_marketplace_banano.json", BANANO) == []  # un solo valor
    assert variants("en_stock_mario_kart.json", MARIO) == []
    assert variants("tarjeta_hites_notebook.json", NOTEBOOK) == []


def test_variant_label():
    ref = hites.normalize(POLERA_TL)
    assert hites.variant_label(ref.external_id, ref.variant_id) == "TL, NARANJA"
    assert hites.variant_label("957877001", "") == ""


@pytest.mark.parametrize(
    "url",
    [
        MARIO,
        "http://hites.com/juego-nintendo-switch-2-mario-kart-world-957877001.html",
        "https://WWW.HITES.COM/Juego-Nintendo-Switch-2-Mario-Kart-World-957877001.html",
        MARIO + "?utm_source=wa&quantity=2&dwopt_957877001_724=0#top",
        MARIO + "?dwvar_957877001_color=",  # selección vacía
        MARIO + "?dwvar_123_color=ROJO",  # selección de otro producto
    ],
)
def test_normaliza_url(url):
    ref = hites.normalize(url)
    assert (ref.external_id, ref.variant_id) == ("957877001", "")
    assert ref.canonical_url == MARIO


def test_normaliza_la_seleccion_en_orden():
    a = hites.normalize(POLERA_TL)
    b = hites.normalize(
        POLERA + "?utm_medium=x&dwvar_954699_Talla-Vestuario-Generica=TL&dwvar_954699_color=NARANJA"
    )
    assert a == b
    assert a.external_id == "954699"
    assert a.canonical_url == (
        POLERA + "?dwvar_954699_Talla-Vestuario-Generica=TL&dwvar_954699_color=NARANJA"
    )
    assert hites.variation_params(a) == {
        "pid": "954699",
        "dwvar_954699_Talla-Vestuario-Generica": "TL",
        "dwvar_954699_color": "NARANJA",
    }


def test_valores_con_espacios():
    ref = hites.normalize(
        "https://www.hites.com/banano-hip-pouch-1l-loam-10059000211.html"
        "?dwvar_10059000211_Talla=TAMANO%20UNICO&dwvar_10059000211_color=AMARILLO"
    )
    assert ref.variant_id == "Talla=TAMANO+UNICO&color=AMARILLO"
    assert hites.variation_params(ref)["dwvar_10059000211_Talla"] == "TAMANO UNICO"
    assert hites.normalize(ref.canonical_url) == ref


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(MARIO).name == "hites"
    assert find_processor(POLERA_TL).name == "hites"
    assert not hites.matches("https://www.hites.com/")
    assert not hites.matches("https://www.hites.com/tecnologia/videojuegos/nintendo/")
    assert not hites.matches("https://www.hites.com/search?q=switch")
    assert not hites.matches("https://www.hites.com/juego-mario-kart.html")
    assert not hites.matches("https://www.hites.com/nintendo/juego-mario-kart-957877001.html")
    assert not hites.matches(
        "https://www.hites.com/on/demandware.store/Sites-HITES-Site/default/Product-Variation"
        "?pid=957877001"
    )
    assert not hites.matches("https://www.hites.com.evil.com/juego-mario-kart-957877001.html")
    assert not hites.matches("https://evilhites.com/juego-mario-kart-957877001.html")
    assert not hites.matches("ftp://www.hites.com/juego-mario-kart-957877001.html")
    with pytest.raises(ValueError):
        hites.normalize("https://www.hites.com/tecnologia/")


@pytest.fixture
def fake_get(monkeypatch):
    """`get_text` falso: {url sin query: respuesta o excepción}."""
    calls = []

    def install(responses):
        async def get_text(url, *, params=None, timeout=30):
            calls.append((url, params))
            result = responses[url]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(hites_mod, "get_text", get_text)
        return calls

    return install


API = "https://www.hites.com/on/demandware.store/Sites-HITES-Site/default/Product-Variation"


async def test_fetch_pide_product_variation(fake_get):
    calls = fake_get({API: fixture_text("hites", "polera_variante_agotada.json")})
    ref = hites.normalize(POLERA_TL)
    r = await hites.fetch(ref)
    assert r.available is False
    assert calls == [(API, hites.variation_params(ref))]


async def test_inexistente_500_en_api_y_404_en_la_ficha(fake_get):
    url = "https://www.hites.com/algo-99999999999.html"
    calls = fake_get({API: FetchError(f"HTTP 500 en {API}"), url: NotFoundError(f"404 en {url}")})
    with pytest.raises(NotFoundError):
        await hites.fetch_raw(hites.normalize(url))
    assert [c[0] for c in calls] == [API, url]


async def test_500_con_ficha_viva_sigue_siendo_error(fake_get):
    fake_get({API: FetchError("HTTP 500"), MARIO: "<html>ficha</html>"})
    with pytest.raises(FetchError) as exc:
        await hites.fetch_raw(hites.normalize(MARIO))
    assert not isinstance(exc.value, NotFoundError)
