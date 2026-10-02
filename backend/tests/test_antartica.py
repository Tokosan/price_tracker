import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.antartica import AntarticaProcessor
from tracker.rules import Reading, check_anomaly

antartica = AntarticaProcessor()
FRANKL = "https://www.antartica.cl/el-hombre-en-busca-del-sentido-9788425432026.html"
DISPAROS = "https://www.antartica.cl/disparos-en-la-oscuridad-9789563143171.html"
HABLAME = "https://www.antartica.cl/hablame-de-amores-9789562476621.html"
AGENDA = "https://www.antartica.cl/agenda-2027-heartstopper-7798083709943.html"


def parse(fixture, url):
    return antartica.parse(fixture_text("antartica", fixture), antartica.normalize(url))


def test_descuento():
    r = parse("descuento_hombre_en_busca.html", FRANKL)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "El Hombre En Busca Del Sentido",
        17408,
        20480,
        "CLP",
        True,
    )
    assert r.image_url.startswith(
        "https://www.antartica.cl/media/catalog/product/9/7/9788425432026_1.jpg?"
    )
    assert "&amp;" not in r.image_url


def test_en_stock_sin_descuento():
    r = parse("en_stock_disparos.html", DISPAROS)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Disparos En La Oscuridad",
        15000,
        None,
        True,
    )


def test_agotado_no_trae_precio_y_no_es_anomalia():
    r = parse("agotado_hablame_de_amores.html", HABLAME)
    assert (r.title, r.price, r.list_price, r.available) == ("Háblame De Amores", None, None, False)
    assert antartica.sold_out_without_price
    reading = Reading(price=r.price, list_price=r.list_price, available=r.available)
    assert check_anomaly(reading, 12000, 80, antartica.sold_out_without_price) is None


def test_preventa_cuenta_como_disponible():
    r = parse("preventa_agenda_heartstopper.html", AGENDA)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Agenda 2027 Heartstopper - PREVENTA",
        17991,
        19990,
        True,
    )


def test_en_stock_sin_precio_es_anomalia():
    raw = fixture_text("antartica", "en_stock_disparos.html").replace(
        'id="product-price-155830"', 'id="otro-precio"'
    )
    r = antartica.parse(raw, antartica.normalize(DISPAROS))
    assert (r.price, r.available) == (None, True)
    reading = Reading(price=r.price, list_price=r.list_price, available=r.available)
    assert check_anomaly(reading, 15000, 80, antartica.sold_out_without_price)[0] == "price_none"


def test_sin_marca_de_stock_es_error_de_lectura():
    raw = fixture_text("antartica", "agotado_hablame_de_amores.html").replace(
        'class="stock unavailable"', 'class="otra-cosa"'
    )
    with pytest.raises(FetchError, match="stock"):
        antartica.parse(raw, antartica.normalize(HABLAME))


def test_no_usa_precios_de_otros_productos_de_la_pagina():
    # Sin el priceBox del producto, los precios de los recomendados no se toman.
    raw = fixture_text("antartica", "descuento_hombre_en_busca.html")
    raw = raw.replace('id="product-price-349879"', "").replace('id="old-price-349879"', "")
    r = antartica.parse(raw, antartica.normalize(FRANKL))
    assert (r.price, r.list_price) == (None, None)


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria_promociones.html", FRANKL)


def test_bloqueo_de_cloudflare_es_error_de_lectura():
    raw = fixture_text("antartica", "bloqueo_cloudflare.html")
    with pytest.raises(FetchError, match="bloqueó") as exc:
        antartica.parse(raw, antartica.normalize(FRANKL))
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize(
    "raw",
    [
        "<html><head><title>Just a moment...</title></head></html>",
        '<html><title>Robot or human?</title><div id="px-captcha"></div></html>',
    ],
)
def test_otros_bloqueos_son_error_de_lectura(raw):
    with pytest.raises(FetchError, match="bloqueó"):
        antartica.parse(raw, antartica.normalize(FRANKL))


@pytest.mark.parametrize(
    "url",
    [
        FRANKL,
        "http://antartica.cl/el-hombre-en-busca-del-sentido-9788425432026.html",
        "https://WWW.ANTARTICA.CL/El-Hombre-En-Busca-Del-Sentido-9788425432026.html?utm_source=x#top",
    ],
)
def test_normaliza_url(url):
    ref = antartica.normalize(url)
    assert (ref.external_id, ref.variant_id) == ("el-hombre-en-busca-del-sentido-9788425432026", "")
    assert ref.canonical_url == FRANKL


def test_url_key_con_sufijo():
    url = "https://www.antartica.cl/carrie-edicion-50-aniversario-9788401035777-771354.html"
    ref = antartica.normalize(url)
    assert ref.external_id == "carrie-edicion-50-aniversario-9788401035777-771354"
    assert ref.canonical_url == url


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(FRANKL).name == "antartica"
    assert find_processor(AGENDA).name == "antartica"
    assert not antartica.matches("https://www.antartica.cl/")
    assert not antartica.matches("https://www.antartica.cl/promociones.html")
    assert not antartica.matches("https://www.antartica.cl/libros/ciencias.html")
    assert not antartica.matches("https://www.antartica.cl/novedades/preventas.html")
    assert not antartica.matches("https://www.antartica.cl/libros/el-hombre-9788425432026.html")
    assert not antartica.matches("https://www.antartica.cl/catalogsearch/result/?q=frankl")
    assert not antartica.matches("https://www.antartica.cl/top-50-2025.html")
    assert not antartica.matches(
        "https://www.antartica.cl.evil.com/el-hombre-en-busca-del-sentido-9788425432026.html"
    )
    assert not antartica.matches(
        "https://evilantartica.cl/el-hombre-en-busca-del-sentido-9788425432026.html"
    )
    with pytest.raises(ValueError):
        antartica.normalize("https://www.antartica.cl/libros.html")
