import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, ProductRef
from tracker.processors.steam import SteamProcessor, steam_to_minor

steam = SteamProcessor()


def test_divide_por_100_en_clp():
    # La API devuelve final: 750000 con currency CLP: son $7.500.
    assert steam_to_minor(750000, "CLP") == 7500


def test_no_divide_en_usd():
    # En USD los centavos ya son la unidad mínima.
    assert steam_to_minor(1999, "USD") == 1999


def test_stardew_valley_fixture_real():
    raw = fixture_text("steam", "stardew_valley.json")
    r = steam.parse(raw, ProductRef("413150", "https://store.steampowered.com/app/413150/"))
    assert r.title == "Stardew Valley"
    assert r.price == 7500
    assert r.currency == "CLP"
    assert r.list_price is None
    assert r.available is True
    assert r.image_url and "413150" in r.image_url


def test_juego_en_oferta_trae_list_price():
    raw = fixture_text("steam", "en_oferta.json")
    r = steam.parse(raw, ProductRef("4019220", "x"))
    assert r.price == 8594
    assert r.list_price == 9549
    assert r.list_price > r.price


def test_juego_gratis():
    raw = fixture_text("steam", "dota2_gratis.json")
    r = steam.parse(raw, ProductRef("570", "x"))
    assert r.price == 0
    assert r.available is True


def test_app_inexistente():
    with pytest.raises(NotFoundError):
        steam.parse('{"999": {"success": false}}', ProductRef("999", "x"))


def test_sin_precio_ni_gratis_queda_sin_precio():
    raw = '{"1": {"success": true, "data": {"name": "Pronto", "is_free": false}}}'
    r = steam.parse(raw, ProductRef("1", "x"))
    assert r.price is None
    assert r.available is False


@pytest.mark.parametrize(
    "url",
    [
        "https://store.steampowered.com/app/413150/Stardew_Valley/",
        "https://store.steampowered.com/app/413150",
        "http://store.steampowered.com/app/413150/?l=spanish",
        "https://store.steampowered.com/agecheck/app/413150/",
    ],
)
def test_normaliza_url(url):
    assert steam.matches(url)
    ref = steam.normalize(url)
    assert ref.external_id == "413150"
    assert ref.canonical_url == "https://store.steampowered.com/app/413150/"


def test_no_matchea_otros_sitios():
    assert not steam.matches("https://store.steampowered.com/bundle/232/")
    assert not steam.matches("https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/")
