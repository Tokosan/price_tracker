from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

ferouch = PROCESSORS["ferouch"]
SLUG = "polo-pique-lt-pink"
POLO = f"https://www.ferouch.cl/{SLUG}/p"


def test_tallas_de_un_color():
    r = parse(ferouch, "polo_tallas_mixtas.json", POLO)
    assert r.title == "Polo Piqué Lt Pink (Talla XXL)"
    assert (r.price, r.list_price, r.available) == (18830, 26900, True)
    assert labels(ferouch, "polo_tallas_mixtas.json", POLO) == [
        "Talla XXL: $18.830",
        "Talla M: $18.830",
        "Talla S: $26.900 (agotada)",
        "Talla XL: $18.830",
        "Talla L: $18.830",
    ]


def test_precio_normal():
    r = parse(ferouch, "bolsa_precio_normal.json", "https://www.ferouch.cl/bolsa-m-30x42cm/p")
    assert (r.title, r.price, r.list_price, r.available) == ("Bolsa M 30x42cm", 500, None, True)


def test_urls():
    check_urls(ferouch, SLUG, "ferouchcl")
