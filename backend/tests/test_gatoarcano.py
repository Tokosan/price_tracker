import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, ProductRef, find_processor
from tracker.processors.gatoarcano import GatoArcanoProcessor
from tracker.rules import Reading, check_anomaly

ga = GatoArcanoProcessor()
BASE = "https://gatoarcano.cl/product"
ROBO = f"{BASE}/robo-rally/"
LORENZO = f"{BASE}/lorenzo-el-magnfico-big-box/"
POKEMON_SLUG = "pokemon-tcg-world-championships-deck-2025-ing"
POKEMON = f"{BASE}/{POKEMON_SLUG}/"


def parse(fixture, url):
    return ga.parse(fixture_text("gatoarcano", fixture), ga.normalize(url))


def test_en_stock():
    r = parse("en_stock_robo_rally.json", ROBO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Robo Rally",
        59990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://gatoarcano.cl/wp-content/uploads/")


def test_oferta_trae_precio_antes():
    r = parse("descuento_lorenzo.json", LORENZO)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Lorenzo el Magnifico Big Box",
        88990,
        94990,
        True,
    )


def test_agotado_con_precio():
    r = parse("agotado_mtg_draft_night.json", f"{BASE}/mtg-reality-fracture-draft-night-ing/")
    assert (r.title, r.price, r.list_price, r.available) == (
        "MTG Draft Night Box – Reality Fracture",
        117990,
        None,
        False,
    )


def test_agotado_en_oferta():
    r = parse(
        "agotado_con_oferta_eclipse.json",
        f"{BASE}/eclipse-el-segundo-amanecer-de-la-galaxia/",
    )
    assert (r.price, r.list_price, r.available) == (196990, 218990, False)


def test_preventa_es_un_producto_comprable():
    # Las preventas son productos normales (categoría `preventas`, con stock).
    data = json.loads(fixture_text("gatoarcano", "preventa_octo_rumble.json"))
    assert "preventas" in [c["slug"] for c in data["products"][0]["categories"]]
    r = parse("preventa_octo_rumble.json", f"{BASE}/octo-rumble/")
    assert (r.title, r.price, r.list_price, r.available) == ("Octo Rumble", 15990, None, True)


@pytest.mark.parametrize(
    ("fixture", "slug", "placeholder", "in_stock"),
    [
        ("proximamente_nyakuza.json", "nyakuza", "1", False),
        ("proximamente_con_stock_swu.json", "swu-homeworlds-booster-display-esp", "0", True),
    ],
)
def test_proximamente_es_agotado_sin_precio(fixture, slug, placeholder, in_stock):
    # "Próximamente": no se puede comprar y trae un precio de relleno ("0" o "1"),
    # a veces con is_in_stock=true. No es un precio ni una anomalía.
    product = json.loads(fixture_text("gatoarcano", fixture))["products"][0]
    assert product["is_purchasable"] is False
    assert (product["prices"]["price"], product["is_in_stock"]) == (placeholder, in_stock)
    r = parse(fixture, f"{BASE}/{slug}/")
    assert (r.price, r.list_price, r.available) == (None, None, False)
    reading = Reading(price=None, list_price=None, available=False)
    assert check_anomaly(reading, 54990, ga.anomaly_drop_pct, ga.sold_out_without_price) is None


def test_variable_con_atributo_global():
    # Los atributos de la variación no vienen en el padre: la selección sale del
    # permalink (`attribute_pa_wcd-2025=<slug del término>`).
    r = parse("variable_agotado_pokemon_wcd.json", POKEMON)
    assert r.title == (
        "Pokémon TCG – World Championships Deck 2025 (ing) (Jose Cruz Galindo Resendiz)"
    )
    assert (r.price, r.available) == (26990, False)
    url = f"{POKEMON}?attribute_pa_wcd-2025=yuya-okita"
    assert parse("variable_agotado_pokemon_wcd.json", url).title.endswith("(Yuya Okita)")
    vs = ga.parse_variants(
        fixture_text("gatoarcano", "variable_agotado_pokemon_wcd.json"), ga.normalize(url)
    )
    assert [(v.label, v.selected) for v in vs] == [
        ("Yuya Okita: $26.990 (agotada)", True),
        ("Jose Cruz Galindo Resendiz: $26.990 (agotada)", False),
        ("Liao Fu Guan: $26.990 (agotada)", False),
        ("Riley Mckay: $26.990 (agotada)", False),
    ]
    for v in vs:
        assert ga.normalize(v.url) == ProductRef(POKEMON_SLUG, v.url, v.variant_id)
    assert vs[0].variant_id == "pa-wcd-2025=yuya-okita"
    with pytest.raises(NotFoundError):
        parse("variable_agotado_pokemon_wcd.json", f"{POKEMON}?attribute_pa_wcd-2025=otro")


def test_producto_simple_no_ofrece_variantes():
    assert (
        ga.parse_variants(
            fixture_text("gatoarcano", "en_stock_robo_rally.json"), ga.normalize(ROBO)
        )
        == []
    )


def test_no_existe():
    raw = json.dumps({"products": [], "variations": []})
    with pytest.raises(NotFoundError):
        ga.parse(raw, ga.normalize(f"{BASE}/no-existe-este-juego/"))


@pytest.mark.parametrize(
    "url",
    [
        LORENZO,
        "https://gatoarcano.cl/product/lorenzo-el-magnfico-big-box",
        "https://www.gatoarcano.cl/product/lorenzo-el-magnfico-big-box/",
        "http://gatoarcano.cl/product/Lorenzo-El-Magnfico-Big-Box/?utm_source=x#reviews",
    ],
)
def test_normaliza_url(url):
    assert ga.normalize(url) == ProductRef("lorenzo-el-magnfico-big-box", LORENZO, "")


def test_matchea_solo_fichas_de_su_dominio():
    assert ga.domain() == "gatoarcano.cl"
    assert find_processor(LORENZO).name == "gatoarcano"
    assert not ga.matches("https://gatoarcano.cl/")
    assert not ga.matches("https://gatoarcano.cl/product/")
    assert not ga.matches("https://gatoarcano.cl/product-category/preventas/")
    assert not ga.matches("https://gatoarcano.cl/product-category/preventas/mtg/")
    assert not ga.matches("https://gatoarcano.cl/producto/robo-rally/")
    assert not ga.matches("https://gatoarcano.cl/?s=robo&post_type=product")
    assert not ga.matches("https://gatoarcano.cl/product/robo-rally/otra-cosa/")
    assert not ga.matches("https://gatoarcano.cl.evil.com/product/robo-rally/")
    assert not ga.matches("https://evilgatoarcano.cl/product/robo-rally/")
    assert not ga.matches("https://www.ecofarmacias.cl/product/robo-rally/")
