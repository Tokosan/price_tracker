from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

caffarena = PROCESSORS["caffarena"]
SLUG = "media-pantalon-pret-a-porte-1046"
MEDIA = f"https://www.caffarena.cl/{SLUG}/p"
POLERA = "https://www.caffarena.cl/polera-algodon-seamless-16906-2g/p"


def test_colores():
    r = parse(caffarena, "media_color_y_talla.json", f"{MEDIA}?skuId=95")
    assert r.title == "Media Pantalón Pret A Porté (Champagne, Talla U)"
    assert (r.price, r.list_price, r.available) == (1490, None, True)
    assert labels(caffarena, "media_color_y_talla.json", MEDIA) == [
        "Grafito, Talla U: $1.490",
        "Champagne, Talla U: $1.490",
    ]


def test_agotado_conserva_el_precio():
    r = parse(caffarena, "polera_agotada.json", POLERA)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polera Algodón Seamless",
        9990,
        None,
        False,
    )


def test_urls():
    check_urls(caffarena, SLUG, "caffarenacl")
