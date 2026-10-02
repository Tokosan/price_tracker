import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.vudugaming import VuduGamingProcessor

vg = VuduGamingProcessor()
BASE = "https://www.vudugaming.cl"
SIERRA = f"{BASE}/sierra-west-espanol"


def parse(fixture, url):
    return vg.parse(fixture_text("vudugaming", fixture), vg.normalize(url))


def test_en_stock():
    r = parse("arknova_dados_en_stock.html", f"{BASE}/arknova-set-de-datos-magenta")
    assert (r.title, r.price, r.currency, r.available) == (
        "Arknova - Set de datos - Magenta",
        3990,
        "CLP",
        True,
    )
    assert r.list_price is None
    assert r.image_url


def test_descuento_trae_precio_final_y_precio_base():
    # Tema nuevo de Jumpseller: sin `#product-price.previous`; el original sale del meta
    # `product:original_price:amount`.
    r = parse("sierra_west_descuento.html", SIERRA)
    assert r.title == "Sierra West - Español"
    assert (r.price, r.list_price, r.available) == (31493, 44990, True)


def test_pagina_en_ingles_da_lo_mismo():
    es = parse("sierra_west_descuento.html", SIERRA)
    en = parse("sierra_west_descuento_en.html", f"{BASE}/en/sierra-west-espanol")
    assert en == es


def test_agotado():
    r = parse("marvel_united_agotado.html", f"{BASE}/marvel-united-x-men-espanol")
    assert (r.price, r.available) == (39990, False)


def test_preventa_abierta_esta_disponible():
    r = parse("nyakuza_preventa.html", f"{BASE}/preventa-nyakuza-espanol")
    assert (r.title, r.price, r.available) == ("Preventa - Nyakuza - Español", 34990, True)


def test_no_disponible_aunque_el_json_ld_diga_instock():
    # Preventa cerrada: el JSON-LD dice InStock, pero el meta dice `pending` y la página
    # muestra "No disponible". El precio es el de la reserva (50 %), no el total.
    raw = fixture_text("vudugaming", "bone_wars_no_disponible.html")
    assert "schema.org/InStock" in raw
    r = vg.parse(raw, vg.normalize(f"{BASE}/bone-wars-espanol"))
    assert (r.price, r.available) == (41495, False)


@pytest.mark.parametrize(
    ("fixture", "url"),
    [
        ("categoria_juegos_de_mesa.html", f"{BASE}/juegos-de-mesa"),
        ("home_en.html", f"{BASE}/en/juegos-de-mesa"),
    ],
)
def test_categoria_y_portada_se_rechazan(fixture, url):
    with pytest.raises(NotFoundError, match="no es una página de producto"):
        parse(fixture, url)


@pytest.mark.parametrize(
    "url",
    [
        SIERRA,
        "https://vudugaming.cl/Sierra-West-Espanol/",
        f"{BASE}/en/sierra-west-espanol",
        f"{BASE}/es/sierra-west-espanol/",
        f"{BASE}/en/sierra-west-espanol?srsltid=AfmBOoq1x2y3",
        "http://www.vudugaming.cl/sierra-west-espanol?utm_source=ig&utm_medium=social#fotos",
    ],
)
def test_normaliza_url(url):
    ref = vg.normalize(url)
    assert ref.external_id == "sierra-west-espanol"
    assert ref.canonical_url == SIERRA


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/",
        f"{BASE}/en/",
        f"{BASE}/en",
        f"{BASE}/en/?srsltid=AfmBOoq1x2y3",
        f"{BASE}/es",
        f"{BASE}/juegos-de-mesa/expansiones",
        f"{BASE}/en/juegos-de-mesa/expansiones",
        f"{BASE}/fr/sierra-west-espanol",
        "https://vudugaming.cl.evil.com/sierra-west-espanol",
        "https://evilvudugaming.cl/sierra-west-espanol",
    ],
)
def test_no_matchea(url):
    assert not vg.matches(url)
    with pytest.raises(ValueError):
        vg.normalize(url)


def test_find_processor():
    assert find_processor(SIERRA).name == "vudugaming"
    assert find_processor(f"{BASE}/en/sierra-west-espanol?srsltid=x").name == "vudugaming"
