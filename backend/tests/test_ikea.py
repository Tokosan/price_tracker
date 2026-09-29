import pytest

from tests.conftest import fixture_text
from tracker.processors.ikea import IkeaProcessor

ikea = IkeaProcessor()
BILLY = "https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/"


def test_billy_en_stock():
    raw = fixture_text("ikea", "billy_blanco.html")
    r = ikea.parse(raw, ikea.normalize(BILLY))
    assert r.title == "BILLY Estante - blanco 80x28x202 cm"
    assert r.price == 59990
    assert r.currency == "CLP"
    assert r.available is True
    assert r.image_url.startswith("https://www.ikea.com/")


def test_billy_variantes_de_color():
    raw = fixture_text("ikea", "billy_blanco.html")
    variants = ikea.parse_variants(raw, ikea.normalize(BILLY))
    ids = {v.external_id: v for v in variants}
    assert set(ids) == {"00263850", "50508652", "10508932"}
    assert ids["00263850"].selected
    assert variants[0].external_id == "00263850"  # la actual va primero
    assert ids["50508652"].label == "Café efecto nogal"
    assert (
        ids["50508652"].url
        == "https://www.ikea.com/cl/es/p/billy-estante-cafe-efecto-nogal-50508652/"
    )


def test_kallax():
    url = "https://www.ikea.com/cl/es/p/kallax-estante-negro-60275812/"
    raw = fixture_text("ikea", "kallax_negro.html")
    ref = ikea.normalize(url)
    r = ikea.parse(raw, ref)
    assert r.price == 44990
    assert r.available is True
    assert {v.external_id for v in ikea.parse_variants(raw, ref)} == {
        "60275812",
        "20275814",
        "60324520",
    }


def test_combinacion_sin_stock():
    url = "https://www.ikea.com/cl/es/p/billy-oxberg-combinacion-estante-puertas-vidrio-cafe-efecto-nogal-s29483540/"
    raw = fixture_text("ikea", "billy_oxberg_sin_stock.html")
    ref = ikea.normalize(url)
    assert ref.external_id == "s29483540"
    r = ikea.parse(raw, ref)
    assert r.available is False
    assert r.price == 259970


def test_pagina_sin_json_ld_da_precio_none():
    r = ikea.parse("<html><body>Mantención</body></html>", ikea.normalize(BILLY))
    assert r.price is None
    assert r.available is False


def test_variantes_por_links_si_falta_el_selector():
    raw = (
        '<a href="https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/">a</a>'
        '<a href="https://www.ikea.com/cl/es/p/billy-estante-efecto-roble-10508932/">b</a>'
        '<a href="https://www.ikea.com/cl/es/p/kallax-estante-negro-60275812/">otro</a>'
    )
    ids = {v.external_id for v in ikea.parse_variants(raw, ikea.normalize(BILLY))}
    assert ids == {"00263850", "10508932"}


@pytest.mark.parametrize(
    ("url", "article"),
    [
        (BILLY, "00263850"),
        ("https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850", "00263850"),
        ("https://ikea.com/cl/es/p/billy-estante-blanco-00263850/?utm=x#content", "00263850"),
        ("https://www.ikea.com/cl/es/p/besta-estante-blanco-s39284998/", "s39284998"),
    ],
)
def test_normaliza_url(url, article):
    assert ikea.matches(url)
    ref = ikea.normalize(url)
    assert ref.external_id == article
    assert ref.canonical_url.startswith("https://www.ikea.com/cl/es/p/")
    assert ref.canonical_url.endswith(f"-{article}/")


def test_no_matchea_otra_region_ni_categorias():
    assert not ikea.matches("https://www.ikea.com/es/es/p/billy-estante-blanco-00263850/")
    assert not ikea.matches("https://www.ikea.com/cl/es/cat/libreros-10382/")
