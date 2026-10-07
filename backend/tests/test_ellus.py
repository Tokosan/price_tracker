from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

ellus = PROCESSORS["ellus"]
JEANS_SLUG = "jeans_hombre_straight_tiro_alto"
JEANS = f"https://www.ellus.cl/{JEANS_SLUG}/p"
BOXERS = "https://www.ellus.cl/boxers_hombre_pack_x3_con_pretina_custom-_blanco-_colores_surtidos/p"


def test_slug_con_guiones_bajos_y_color_unico():
    # Todos los items son NEGRO: el color no aparece en la etiqueta.
    r = parse(ellus, "jeans_talla_y_color.json", JEANS)
    assert r.title == "Jeans Hombre Straight Básico Tiro Alto (Talla 40)"
    assert (r.price, r.list_price, r.available) == (19990, 36990, True)
    agotada = parse(ellus, "jeans_talla_y_color.json", f"{JEANS}?skuId=4518")
    assert (agotada.price, agotada.list_price, agotada.available) == (36990, None, False)


def test_talla_y_color():
    assert labels(ellus, "boxers_2x1.json", BOXERS)[:3] == [
        "Azul, Talla S: $8.990",
        "Rojo, Talla S: $8.990",
        "Rojo, Talla M: $8.990",
    ]


def test_promocion_2x1_se_ignora():
    # El teaser "2x1 Boxers" no cambia `Price`.
    r = parse(ellus, "boxers_2x1.json", f"{BOXERS}?skuId=7540")
    assert r.title == "Boxers Hombre Pack x3 con Pretina Custom (Negro, Talla S)"
    assert (r.price, r.list_price, r.available) == (8990, 14990, True)


def test_urls():
    check_urls(ellus, JEANS_SLUG, "elluscl")
