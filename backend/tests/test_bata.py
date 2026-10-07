import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import bata as bata_mod
from tracker.processors.bata import BataProcessor

bata = BataProcessor()
POLAR = (
    "https://www.bata.com/cl/mujer/vestuario/polars/"
    "polar-mujer-weinbrenner-cota--701M_2024_9136031.html"
)
POLAR_CANONICO = "https://www.bata.com/cl/701M_2024_9136031.html"
POLAR_XXS = POLAR + "?dwvar_701M__2024__9136031_color=48&dwvar_701M__2024__9136031_size=9350"
NORTH_STAR = (
    "https://www.bata.com/cl/hombre/calzado/zapatillas/"
    "zapatilla-hombre-north-star-victory--701M_2026_8516356.html"
)
NORTH_STAR_41 = (
    NORTH_STAR + "?dwvar_701M__2026__8516356_color=48&dwvar_701M__2026__8516356_size=8F40"
)


def parse(fixture, url):
    return bata.parse(fixture_text("bata", fixture), bata.normalize(url))


def variants(fixture, url):
    return bata.parse_variants(fixture_text("bata", fixture), bata.normalize(url))


def test_grupo_sin_talla_con_descuento():
    r = parse("grupo_sin_talla_descuento.json", POLAR)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polar Mujer Weinbrenner Cota",
        13990,
        29990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.bata.com/dw/image/")


def test_talla_agotada():
    r = parse("talla_agotada.json", POLAR_XXS)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polar Mujer Weinbrenner Cota (Talla: XXS)",
        13990,
        29990,
        False,
    )


def test_talla_en_stock():
    r = parse("north_star_talla_en_stock.json", NORTH_STAR_41)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zapatilla Hombre North Star Victory (Talla: 41)",
        22990,
        36990,
        True,
    )


def test_seleccion_que_no_existe_es_error_de_lectura():
    raw = fixture_text("bata", "north_star_talla_en_stock.json")
    url = NORTH_STAR + "?dwvar_701M__2026__8516356_color=48&dwvar_701M__2026__8516356_size=8F50"
    with pytest.raises(FetchError, match="ya no existe"):
        bata.parse(raw, bata.normalize(url))


def test_variantes_desde_el_grupo_sin_talla():
    vs = variants("north_star_sin_talla.json", NORTH_STAR)
    assert vs[0].selected and vs[0].label == "Cualquier talla"
    assert (vs[0].url, vs[0].variant_id) == ("https://www.bata.com/cl/701M_2026_8516356.html", "")
    labels = [v.label for v in vs[1:]]
    # La ficha muestra solo 39 a 44: las otras tallas están agotadas.
    assert labels == [
        "Talla: 38 (no disponible)",
        *(f"Talla: {n}" for n in range(39, 45)),
        *(f"Talla: {n} (no disponible)" for n in range(45, 49)),
    ]
    assert vs[1].url == (
        "https://www.bata.com/cl/701M_2026_8516356.html"
        "?dwvar_701M__2026__8516356_color=48&dwvar_701M__2026__8516356_size=8F10"
    )
    for v in vs:
        ref = bata.normalize(v.url)
        assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
            v.external_id,
            v.variant_id,
            v.url,
        )


def test_variantes_solo_cambian_la_talla():
    # El maestro lista otros colores (no elegibles en este grupo): no se ofrecen.
    vs = variants("talla_agotada.json", POLAR_XXS)
    assert vs[0].selected and vs[0].label == "Talla: XXS (no disponible)"
    assert all(v.label.startswith("Talla: ") for v in vs)
    assert len(vs) == 8


@pytest.mark.parametrize(
    "url",
    [
        POLAR,
        POLAR_CANONICO,
        "https://www.bata.com/cl/polar-mujer-weinbrenner-cota--701M_2024_9136031.html",
        "https://WWW.BATA.COM/cl/Mujer/polar-mujer-weinbrenner-cota--701m_2024_9136031.html",
        POLAR + "?utm_source=x&dwvar_701M_2024_9136031_size=9380",  # sin duplicar `_`: no
        # El link de una talla (pid con `_08`) se sigue como su grupo.
        "https://www.bata.com/cl/mujer/vestuario/polars/"
        "polar-mujer-weinbrenner-cota--701M_2024_9136031_08.html",
    ],
)
def test_normaliza_url(url):
    ref = bata.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "701M_2024_9136031",
        "",
        POLAR_CANONICO,
    )


def test_normaliza_la_seleccion_con_guiones_bajos_duplicados():
    ref = bata.normalize(POLAR_XXS)
    assert ref.variant_id == "color=48&size=9350"
    assert ref.canonical_url == POLAR_CANONICO + (
        "?dwvar_701M__2024__9136031_color=48&dwvar_701M__2024__9136031_size=9350"
    )
    assert bata.normalize(ref.canonical_url) == ref
    assert bata.variation_params(ref) == {
        "pid": "701M_2024_9136031",
        "dwvar_701M__2024__9136031_color": "48",
        "dwvar_701M__2024__9136031_size": "9350",
    }


def test_maestro_de_todos_los_colores():
    ref = bata.normalize(
        "https://www.bata.com/cl/polar-mujer-weinbrenner-cota--701M_079130316208IR.html"
    )
    assert (ref.external_id, ref.canonical_url) == (
        "701M_079130316208IR",
        "https://www.bata.com/cl/701M_079130316208IR.html",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(POLAR).name == "bata"
    assert find_processor(NORTH_STAR_41).name == "bata"
    assert not bata.matches("https://www.bata.com/cl/")
    assert not bata.matches("https://www.bata.com/cl/marcas/north-star/")
    assert not bata.matches("https://www.bata.com/cl/privacidad.html")
    assert not bata.matches("https://www.bata.com/cl/search?q=polar")
    # Otros países de bata.com no son la tienda de Chile.
    assert not bata.matches("https://www.bata.com/it/polar-701M_2024_9136031.html")
    assert not bata.matches(
        "https://www.bata.com/on/demandware.store/Sites-bata-cl-Site/es_CL/"
        "Product-Variation?pid=701M_2024_9136031"
    )
    assert not bata.matches("https://www.bata.com.evil.com/cl/polar--701M_2024_9136031.html")
    assert not bata.matches("https://evilbata.com/cl/polar--701M_2024_9136031.html")
    with pytest.raises(ValueError):
        bata.normalize("https://www.bata.com/cl/mujer/")


API = "https://www.bata.com/on/demandware.store/Sites-bata-cl-Site/es_CL/Product-Variation"


@pytest.fixture
def fake_get(monkeypatch):
    """`get_text_impersonate` falso (Bata se pide con curl_cffi)."""
    calls = []

    def install(responses):
        async def get_text_impersonate(url, *, params=None, timeout=30):
            calls.append((url, params))
            result = responses[url]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(bata_mod, "get_text_impersonate", get_text_impersonate)
        return calls

    return install


async def test_fetch_pide_product_variation_con_curl_cffi(fake_get):
    calls = fake_get({API: fixture_text("bata", "talla_agotada.json")})
    ref = bata.normalize(POLAR_XXS)
    assert (await bata.fetch(ref)).available is False
    assert calls == [(API, bata.variation_params(ref))]


async def test_inexistente_500_en_api_y_404_en_la_ficha(fake_get):
    url = "https://www.bata.com/cl/701M_2024_9999999.html"
    calls = fake_get({API: FetchError("HTTP 500"), url: NotFoundError(f"404 en {url}")})
    with pytest.raises(NotFoundError):
        await bata.fetch_raw(bata.normalize(url))
    assert [c[0] for c in calls] == [API, url]
