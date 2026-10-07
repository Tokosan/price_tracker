from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

ae = PROCESSORS["americaneagle"]
POLERA_SLUG = "polera-ae-playera-ligera-lisa-11641539001"
POLERA = f"https://www.ae.cl/{POLERA_SLUG}/p"
JEANS_SLUG = "jeans-ae-airflex--slim-con-parches-y-fibras-de-tencel™-01176308252"
JEANS = (
    "https://www.ae.cl/jeans-ae-airflex--slim-con-parches-y-fibras-de-tencel%E2%84%A2-01176308252/p"
)


def test_tallas():
    r = parse(ae, "polera_tallas_mixtas.json", POLERA)
    assert r.title == "Polera Super Soft Icon American Eagle (Talla M)"
    assert (r.price, r.list_price, r.available) == (9990, 22990, True)
    assert labels(ae, "polera_tallas_mixtas.json", POLERA)[-2:] == [
        "Talla XS: $22.990 (agotada)",
        "Talla XXL: $22.990 (agotada)",
    ]


def test_talla_repetida_se_distingue_por_sku():
    # Dos lavados del mismo jeans en una ficha, sin atributo de color: cada talla aparece dos
    # veces (con otra foto) y la base agrega el SKU.
    assert ae.normalize(JEANS).external_id == JEANS_SLUG
    r = parse(ae, "jeans_slug_tm.json", f"{JEANS}?skuId=47380")
    assert r.title.endswith("TENCEL™ (Talla 36/30, SKU 47380)")
    assert (r.price, r.list_price, r.available) == (24990, 49990, True)
    lbls = labels(ae, "jeans_slug_tm.json", JEANS)
    assert len(lbls) == 38 and lbls[0] == "Talla 34/34, SKU 47379: $49.990 (agotada)"


def test_urls():
    check_urls(ae, POLERA_SLUG, "americaneaglecl")
