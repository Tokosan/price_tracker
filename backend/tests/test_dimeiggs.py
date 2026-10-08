"""Dimeiggs: respuestas reales de la API del catálogo de VTEX (cuenta dimeiggsschl)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.dimeiggs import DimeiggsProcessor

dm = DimeiggsProcessor()
FORRO = "https://www.dimeiggs.cl/forro-para-cuaderno-college-rosado-dimeiggs/p"
PAPEL = "https://www.dimeiggs.cl/papel-fotocopia-75-gramos-500-hojas-ovella/p"


def parse(fixture, url):
    return dm.parse(fixture_text("dimeiggs", fixture), dm.normalize(url))


def test_descuento():
    # La ficha muestra $320 con el descuento y $450 como precio normal.
    r = parse("descuento.json", FORRO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Forro  Cuaderno College Rosado Plastico Murano",  # doble espacio de la tienda
        320,
        450,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://dimeiggsschl.vteximg.com.br/")


def test_agotado_conserva_el_precio():
    r = parse("agotado.json", PAPEL)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Papel Fotocopia Carta 75 Gramos 500 Hojas Ovella",
        3890,
        None,
        False,
    )


def test_slug_inexistente():
    with pytest.raises(NotFoundError):
        dm.parse("[]", dm.normalize(FORRO))


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dimeiggs.cl.evil.com/forro-para-cuaderno-college-rosado-dimeiggs/p",
        "https://www.dimeiggs.cl/escolar/cuadernos",
    ],
)
def test_no_matchea(url):
    assert not dm.matches(url)


def test_registrado():
    assert (
        find_processor("https://dimeiggs.cl/forro-para-cuaderno-college-rosado-dimeiggs/p").name
        == "dimeiggs"
    )
