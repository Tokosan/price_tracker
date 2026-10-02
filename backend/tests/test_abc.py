import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.abc import AbcProcessor

abc = AbcProcessor()
ZAPATILLA = "https://www.abc.cl/zapatilla-lona-hombre-icono/28767943.html"
AGOTADA = "https://www.abc.cl/zapatilla-lona-hombre-icono/28767889.html"
COMBO = (
    "https://www.abc.cl/combo-cama-europea-celta-2-plazas-bd-cadiz-respaldo-2-veladores-"
    "casanova-2-plazas-pack-almohadas-casa-linda/29914.html"
)
TV = "https://www.abc.cl/smart-tv-qled-65-hisense-4k-vidaa-65qd5sv/29235937.html"


def parse(fixture, url):
    return abc.parse(fixture_text("abc", fixture), abc.normalize(url))


def test_descuento():
    r = parse("descuento_zapatilla.html", ZAPATILLA)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatilla Lona Hombre Icono",
        5500,
        19990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.abc.cl/on/demandware.static/")


def test_agotado():
    r = parse("agotado_zapatilla.html", AGOTADA)
    assert (r.price, r.list_price, r.available) == (5500, 19990, False)


def test_ignora_el_precio_con_tarjeta():
    raw = fixture_text("abc", "tarjeta_tv_hisense.html")
    assert "js-tlp-price" in raw and 'data-value="419990.0"' in raw
    r = abc.parse(raw, abc.normalize(TV))
    assert r.title == 'Smart TV QLED 65" Hisense 4K VIDAA 65QD5SV'
    assert (r.price, r.list_price, r.available) == (429990, 769990, True)


def test_bundle_usa_el_precio_del_combo_y_no_el_de_sus_componentes():
    r = parse("bundle_combo_cama.html", COMBO)
    assert r.title.startswith("Combo Cama Europea Celta 2 Plazas")
    # Los componentes traen "Normal" 309.990, 69.990…; el combo no tiene precio tachado.
    assert (r.price, r.list_price, r.available) == (396970, None, True)


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError, match=r"product\.group"):
        parse("categoria_refrigeradores.html", ZAPATILLA)


def test_sin_internet_usa_el_normal():
    raw = fixture_text("abc", "descuento_zapatilla.html").replace(
        "js-internet-price", "js-otro-price"
    )
    r = abc.parse(raw, abc.normalize(ZAPATILLA))
    assert (r.price, r.list_price) == (19990, None)


def test_sin_boton_no_inventa_precio():
    raw = fixture_text("abc", "descuento_zapatilla.html").replace(
        'class="add-to-cart', 'class="otro-boton'
    )
    r = abc.parse(raw, abc.normalize(ZAPATILLA))
    assert (r.price, r.list_price, r.available) == (None, None, False)


def test_link_del_maestro_con_variantes_pide_el_de_la_variante():
    # El maestro (…/638317.html, el canonical de sus variantes) muestra la ficha de una
    # variante por defecto, con su propio data-pid: no se sigue en silencio otra talla.
    maestro = "https://www.abc.cl/zapatilla-lona-hombre-icono/638317.html"
    with pytest.raises(NotFoundError, match="pega el link de la talla"):
        parse("descuento_zapatilla.html", maestro)


def test_pagina_sin_bloque_de_producto_es_error_de_lectura():
    with pytest.raises(FetchError):
        abc.parse('<meta property="og:type" content="product">', abc.normalize(ZAPATILLA))


@pytest.mark.parametrize(
    "url",
    [
        ZAPATILLA,
        "https://www.abc.cl/28767943.html",
        "http://abc.cl/Zapatilla-Lona-Hombre-Icono/28767943.html?utm_source=wa#top",
        "https://www.lapolar.cl/zapatilla-lona-hombre-icono/28767943.html",
        "https://lapolar.cl/28767943.html",
        "https://www.abcdin.cl/28767943.html?quantity=1",
        "https://ABCDIN.CL/a/b/28767943.html",
        ZAPATILLA + "?dwvar_28767943_color=Negro",  # abc no usa la selección
    ],
)
def test_normaliza_url(url):
    ref = abc.normalize(url)
    assert (ref.external_id, ref.variant_id) == ("28767943", "")
    assert ref.canonical_url == "https://www.abc.cl/28767943.html"


def test_matchea_solo_fichas_de_sus_dominios():
    assert find_processor(ZAPATILLA).name == "abc"
    assert find_processor("https://www.lapolar.cl/29914.html").name == "abc"
    assert not abc.matches("https://www.abc.cl/")
    assert not abc.matches("https://www.abc.cl/linea-blanca/refrigeradores/")
    assert not abc.matches("https://www.abc.cl/search?q=tv")
    assert not abc.matches("https://www.abc.cl/zapatilla-lona-hombre-icono.html")
    assert not abc.matches("https://www.abc.cl/123.html")  # ID demasiado corto
    assert not abc.matches("https://www.abc.cl.evil.com/zapatilla/28767943.html")
    assert not abc.matches("https://evilabc.cl/zapatilla/28767943.html")
    assert not abc.matches("https://www.lapolar.cl.evil.com/28767943.html")
    assert not abc.matches("https://www.hites.com/zapatilla-28767943.html")
    with pytest.raises(ValueError):
        abc.normalize("https://www.abc.cl/linea-blanca/")
