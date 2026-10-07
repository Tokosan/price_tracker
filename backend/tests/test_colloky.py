from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

colloky = PROCESSORS["colloky"]
SLUG = "zapatilla-deportiva-nina-azul-21-27"
ZAP = f"https://www.colloky.cl/{SLUG}/p"


def test_tallas():
    r = parse(colloky, "zapatilla_tallas_mixtas.json", ZAP)
    assert r.title == "Zapatilla deportiva niña azul 21-27 (Talla 21)"
    assert (r.price, r.list_price, r.available) == (12495, 24990, True)
    assert labels(colloky, "zapatilla_tallas_mixtas.json", ZAP)[-2:] == [
        "Talla 26: $24.990 (agotada)",
        "Talla 27: $24.990 (agotada)",
    ]


def test_urls():
    # La cuenta VTEX es la de Colgram, la empresa dueña de la marca.
    check_urls(colloky, SLUG, "colgramcl")
