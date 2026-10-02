import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, find_processor
from tracker.processors.lider import LiderProcessor

lider = LiderProcessor()
PILLOWS = "https://super.lider.cl/ip/cereales/00780242000793"


def parse(fixture, url=PILLOWS):
    return lider.parse(fixture_text("lider", fixture), lider.normalize(url))


def test_en_stock():
    r = parse("pillows_en_stock.html")
    assert (r.title, r.price, r.currency, r.available) == (
        "Cereales Pillows Sabor Chocolate, 350 g",
        3690,
        "CLP",
        True,
    )
    assert r.list_price is None
    assert r.image_url.startswith("https://i5.walmartimages.cl/")


def test_descuento_trae_precio_antes():
    r = parse("monoballs_descuento.html", "https://super.lider.cl/ip/cereales/00780221516889")
    assert r.title == "Cereal Mono Balls, 400 g"
    assert (r.price, r.list_price, r.available) == (2790, 3290, True)


def test_agotado():
    r = parse("granola_agotado.html", "https://super.lider.cl/ip/cereales/00780467391367")
    assert r.available is False
    assert (r.price, r.list_price) == (4550, 5390)


def test_granel_se_marca_por_kg():
    r = parse("palta_granel.html", "https://super.lider.cl/ip/frutas/00203030000000")
    assert r.title == "Palta hass granel (por kg)"
    assert (r.price, r.available) == (6290, True)


def test_captcha_es_error_de_lectura():
    with pytest.raises(FetchError, match="PerimeterX"):
        parse("bloqueado.html")


def test_sin_next_data_usa_json_ld():
    raw = fixture_text("lider", "monoballs_descuento.html").replace("__NEXT_DATA__", "x")
    r = lider.parse(raw, lider.normalize(PILLOWS))
    assert (r.title, r.price, r.available) == ("Cereal Mono Balls, 400 g", 2790, True)
    assert r.list_price is None


def test_pagina_sin_producto_da_precio_none():
    r = lider.parse("<html><title>Lider</title></html>", lider.normalize(PILLOWS))
    assert r.price is None and r.available is False


@pytest.mark.parametrize(
    "url",
    [
        PILLOWS,
        "https://super.lider.cl/ip/00780242000793",
        "https://super.lider.cl/ip/lo-que-sea/00780242000793/",
        "http://SUPER.lider.cl/ip/cereales/00780242000793?utm_source=wa#top",
    ],
)
def test_normaliza_url(url):
    ref = lider.normalize(url)
    assert ref.external_id == "00780242000793"
    assert ref.canonical_url == "https://super.lider.cl/ip/00780242000793"


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(PILLOWS).name == "lider"
    assert not lider.matches("https://super.lider.cl/")
    assert not lider.matches("https://super.lider.cl/browse/despensa/cereales/cereales-y-avenas")
    assert not lider.matches("https://super.lider.cl/search?q=cereal")
    assert not lider.matches("https://super.lider.cl/ip/cereales/pillows")
    assert not lider.matches("https://super.lider.cl.evil.com/ip/cereales/00780242000793")
    assert not lider.matches("https://evilsuper.lider.cl/ip/cereales/00780242000793")


# --- Mercadería general (www.lider.cl) ---

FREIDORA = (
    "https://www.lider.cl/ip/electrodomesticos-cocina/"
    "freidora-de-aire-y-vapor-telefunken-7lts-easyfryer-st/00779835787365"
)


def test_www_en_stock_con_descuento():
    # Vendedor externo (marketplace, 101dB Chile): $64.990, antes $109.990.
    r = parse("www_freidora.html", FREIDORA)
    assert r.title == "Freidora de Aire y Vapor Telefunken 7lts EasyFryer ST"
    assert (r.price, r.list_price, r.currency, r.available) == (64990, 109990, "CLP", True)
    assert r.image_url.startswith("https://i5.walmartimages.cl/")


def test_www_agotado_con_descuento():
    r = parse(
        "www_cocina_descuento.html",
        "https://www.lider.cl/ip/cocinas/cocina-a-gas-4-platos-negra-mv-120-t/00780731184421",
    )
    assert r.title == "Cocina Gas licuado / Gas natural 4 Quemadores MV 120 T"
    assert (r.price, r.list_price, r.available) == (189990, 259990, False)


def test_www_agotado_sin_descuento():
    r = parse(
        "www_secadora.html",
        "https://www.lider.cl/ip/lavado-y-planchado/secadora-frontal-blanca-10-kg-sem101bdby/00075763837274",
    )
    assert r.title == "Secadora Evacuación 10 KG SEM101BDBY"
    assert (r.price, r.list_price, r.available) == (277990, None, False)


def test_www_tv_agotado():
    r = parse(
        "www_tv_agotado.html",
        "https://www.lider.cl/ip/tv/televisor-75-led-4k-uhd-75a6nv-smart-tv-hisense/00694235141014",
    )
    assert r.title == 'Televisor 75" LED 4K UHD 75A6NV Smart TV Hisense'
    assert (r.price, r.list_price, r.available) == (549990, 879990, False)


@pytest.mark.parametrize(
    "url",
    [
        FREIDORA,
        "https://www.lider.cl/ip/00779835787365",
        "https://www.lider.cl/ip/electrodomesticos-cocina/00779835787365/",
        "https://lider.cl/ip/electrodomesticos-cocina/00779835787365",
        "http://WWW.LIDER.CL/ip/Electrodomesticos-Cocina/Freidora/00779835787365?utm_source=x#top",
        f"  {FREIDORA}  ",
    ],
)
def test_www_conserva_el_host_y_lleva_prefijo(url):
    ref = lider.normalize(url)
    assert ref.external_id == "www:00779835787365"
    assert ref.canonical_url == "https://www.lider.cl/ip/00779835787365"
    assert ref.variant_id == ""


def test_super_con_slug_sigue_igual():
    # Los Products del súper no cambian de external_id ni de URL.
    ref = lider.normalize("https://super.lider.cl/ip/cereales/cereales-pillows/00780242000793")
    assert ref.external_id == "00780242000793"
    assert ref.canonical_url == "https://super.lider.cl/ip/00780242000793"


def test_mismo_id_en_los_dos_hosts_son_productos_distintos():
    sup = lider.normalize("https://super.lider.cl/ip/00694235141014")
    www = lider.normalize("https://www.lider.cl/ip/00694235141014")
    assert sup.external_id != www.external_id
    assert sup.canonical_url != www.canonical_url


async def test_www_se_lee_en_su_host(monkeypatch):
    urls = []

    async def fake_get_text(url, **kwargs):
        urls.append(url)
        return fixture_text("lider", "www_freidora.html")

    monkeypatch.setattr("tracker.processors.lider.get_text", fake_get_text)
    r = await lider.fetch(lider.normalize(FREIDORA))
    assert urls == ["https://www.lider.cl/ip/00779835787365"]
    assert r.price == 64990


@pytest.mark.parametrize(
    "url",
    [
        "https://www.lider.cl/",
        "https://www.lider.cl/catalogo/v/freidora-de-aire-de-5-litros",
        "https://www.lider.cl/browse/electrohogar/cocinas",
        "https://www.lider.cl/search?q=freidora",
        "https://www.lider.cl/ip/cocinas/cocina-a-gas",
        "https://www.lider.cl.evil.com/ip/cocinas/00780731184421",
        "https://evillider.cl/ip/cocinas/00780731184421",
        "https://www.evil.lider.cl/ip/cocinas/00780731184421",
        "https://tienda.lider.cl/ip/cocinas/00780731184421",
        "https://www.lider.cl/ip/a/b/c/d/00780731184421",
    ],
)
def test_www_no_matchea(url):
    assert not lider.matches(url)
    with pytest.raises(ValueError):
        lider.normalize(url)
