import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.lafortaleza import LaFortalezaProcessor

lf = LaFortalezaProcessor()
FROSTHAVEN = "https://www.lafortalezapuq.cl/frosthaven"


def parse(fixture, url=FROSTHAVEN):
    return lf.parse(fixture_text("lafortaleza", fixture), lf.normalize(url))


def test_en_stock():
    r = parse("frosthaven_en_stock.html")
    assert (r.title, r.price, r.currency, r.available) == ("Frosthaven", 249990, "CLP", True)
    assert r.list_price is None
    assert r.image_url


def test_descuento_trae_precio_final_y_precio_base():
    r = parse("azul_descuento.html", "https://www.lafortalezapuq.cl/azul-jardin-de-la-reina")
    assert r.title == "Azul: El jardín de la Reina"
    assert (r.price, r.list_price) == (26994, 44990)


def test_agotado_por_json_ld():
    # No se encontró un agotado real (la tienda los oculta de las categorías): se
    # simula con la marca que usa schema.org en el JSON-LD y en el meta.
    raw = fixture_text("lafortaleza", "frosthaven_en_stock.html")
    raw = raw.replace("schema.org/InStock", "schema.org/OutOfStock").replace(
        'content="instock"', 'content="oos"'
    )
    r = lf.parse(raw, lf.normalize(FROSTHAVEN))
    assert r.available is False and r.price == 249990


def test_agotado_real():
    r = parse("splendor_marvel_agotado.html", "https://www.lafortalezapuq.cl/splendor-marvel")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Splendor: Marvel",
        39990,
        None,
        False,
    )


def test_categoria_se_rechaza():
    url = "https://www.lafortalezapuq.cl/accesorios"
    with pytest.raises(NotFoundError, match="no es una página de producto"):
        parse("categoria_accesorios.html", url)


def test_solo_meta_tags():
    raw = (
        '<meta property="og:type" content="product">'
        '<meta property="og:title" content="Juego ">'
        '<meta property="product:price:amount" content="12990.0">'
        '<meta property="product:price:currency" content="CLP">'
        '<meta property="product:availability" content="instock">'
    )
    r = lf.parse(raw, lf.normalize(FROSTHAVEN))
    assert (r.title, r.price, r.available) == ("Juego", 12990, True)


@pytest.mark.parametrize(
    "url",
    [
        FROSTHAVEN,
        "https://lafortalezapuq.cl/Frosthaven/",
        "http://www.lafortalezapuq.cl/frosthaven?utm_source=ig#fotos",
    ],
)
def test_normaliza_url(url):
    ref = lf.normalize(url)
    assert ref.external_id == "frosthaven"
    assert ref.canonical_url == FROSTHAVEN


def test_matchea_solo_su_dominio_y_un_slug():
    assert find_processor(FROSTHAVEN).name == "lafortaleza"
    assert not lf.matches("https://www.lafortalezapuq.cl/")
    assert not lf.matches("https://www.lafortalezapuq.cl/juegos/frosthaven")
    assert not lf.matches("https://lafortalezapuq.cl.evil.com/frosthaven")
