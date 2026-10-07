from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

opaline = PROCESSORS["opaline"]
SLUG = "conjunto-3-piezas-beige-bebe-unisex"
CONJUNTO = f"https://www.opaline.cl/{SLUG}/p"


def test_tallas_de_bebe():
    r = parse(opaline, "conjunto_tallas_mixtas.json", CONJUNTO)
    assert r.title == "Conjunto 3 Piezas Beige Bebe Unisex (Talla PR)"
    assert (r.price, r.list_price, r.available) == (14995, 29990, True)
    assert labels(opaline, "conjunto_tallas_mixtas.json", CONJUNTO)[:3] == [
        "Talla PR: $14.995",
        "Talla RN: $29.990 (agotada)",
        "Talla 3M: $29.990 (agotada)",
    ]


def test_urls():
    check_urls(opaline, SLUG, "opalinecl")
