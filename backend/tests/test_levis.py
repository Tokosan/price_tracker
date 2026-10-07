from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

levis = PROCESSORS["levis"]
JEANS_SLUG = "jeans-hombre-levis-505-regular-00505-3437"
JEANS = f"https://www.levi.cl/{JEANS_SLUG}/p"
AGOTADO = "https://www.levi.cl/jeans-hombre-levis-505-regular-00505-1469/p"
PANTALON = "https://www.levi.cl/pantalon-hombre-levis-568-loose-carpenter-55849-0085/p"


def test_jeans_por_cintura_y_largo():
    r = parse(levis, "jeans_505_tallas_mixtas.json", f"{JEANS}?skuId=52936")
    assert r.title == "Jeans Hombre Levi's 505 Regular (Cintura 38, Largo 30)"
    assert (r.price, r.list_price, r.available) == (29990, 64990, True)
    assert labels(levis, "jeans_505_tallas_mixtas.json", JEANS)[:2] == [
        "Cintura 34, Largo 30: $64.990 (agotada)",
        "Cintura 30, Largo 30: $64.990 (agotada)",
    ]


def test_todas_las_tallas_agotadas():
    # Respuesta de `fq=productId` (la búsqueda por slug da []): ver test_vtex_apparel.
    r = parse(levis, "jeans_505_agotado.json", f"{AGOTADO}?skuId=376")
    assert r.title == "Jeans Hombre Levi's 505 Regular (Cintura 31, Largo 30)"
    assert (r.price, r.list_price, r.available) == (59990, None, False)
    lbls = labels(levis, "jeans_505_agotado.json", AGOTADO)
    assert len(lbls) == 30 and all(lbl.endswith("(agotada)") for lbl in lbls)


def test_precio_normal():
    r = parse(levis, "pantalon_precio_normal.json", PANTALON)
    assert r.title == "Pantalón Hombre Levi's 568 Loose Carpenter (Cintura 34, Largo 30)"
    assert (r.price, r.list_price, r.available) == (79990, None, True)


def test_urls():
    check_urls(levis, JEANS_SLUG, "leviscl")
