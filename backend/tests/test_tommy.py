from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

tommy = PROCESSORS["tommy"]
ZAP_SLUG = "zapatillas-acabado-granulado-fm0fm05367dw5"
ZAP = f"https://cl.tommy.com/{ZAP_SLUG}/p"
# El slug trae un espacio duro (U+00A0) que viene del nombre del producto.
CAMISETAS_SLUG = "pack-3-camisetas-cuello-redondo-logo\xa0-09tcr01965"
CAMISETAS = "https://cl.tommy.com/pack-3-camisetas-cuello-redondo-logo%C2%A0-09tcr01965/p"


def test_tallas_con_y_sin_stock():
    r = parse(tommy, "zapatillas_tallas_mixtas.json", f"{ZAP}?skuId=148809")
    assert r.title == "Zapatillas Court Detail (Talla 43)"
    assert (r.price, r.list_price, r.available) == (55993, 79990, True)
    assert labels(tommy, "zapatillas_tallas_mixtas.json", ZAP) == [
        "Talla 40: $79.990 (agotada)",
        "Talla 41: $79.990 (agotada)",
        "Talla 42: $55.993",
        "Talla 43: $55.993",
        "Talla 44: $55.993",
        "Talla 45: $79.990 (agotada)",
    ]


def test_slug_con_espacio_duro():
    ref = tommy.normalize(CAMISETAS)
    assert (ref.external_id, ref.canonical_url) == (CAMISETAS_SLUG, CAMISETAS)
    r = parse(tommy, "camisetas_slug_espacio_duro.json", CAMISETAS)
    assert r.title == "Pack De 3 Camisetas C-Neck (Talla S)"
    assert (r.price, r.list_price, r.available) == (31992, 39990, True)


def test_urls():
    check_urls(tommy, ZAP_SLUG, "tommychile")
    assert not tommy.matches(f"https://tommy.com/{ZAP_SLUG}/p")
    assert not tommy.matches(f"https://us.tommy.com/{ZAP_SLUG}/p")
