from tests.vtex_apparel_helpers import check_urls, labels, parse, variants
from tracker.processors import PROCESSORS

ck = PROCESSORS["calvinklein"]
SLIP_SLUG = "pack-3-hip-brief-intense-power-nb3607924"
SLIP = f"https://www.calvinklein.cl/{SLIP_SLUG}/p"
BOLSA = "https://www.calvinklein.cl/bolsa-pequena-clck12462-os/p"


def test_tallas_en_oferta_y_agotada():
    r = parse(ck, "hip_brief_tallas_mixtas.json", SLIP)
    assert r.title == "Pack de 3 Slips Intense Power (Talla S)"
    assert (r.price, r.list_price, r.available) == (29994, 49990, True)
    assert labels(ck, "hip_brief_tallas_mixtas.json", SLIP) == [
        "Talla S: $29.994",
        "Talla M: $29.994",
        "Talla L: $29.994",
        "Talla XL: $49.990 (agotada)",
    ]
    xl = parse(ck, "hip_brief_tallas_mixtas.json", f"{SLIP}?skuId=67313")
    assert (xl.price, xl.list_price, xl.available) == (49990, None, False)


def test_producto_sin_atributos():
    r = parse(ck, "bolsa_precio_normal.json", BOLSA)
    assert (r.title, r.price, r.list_price, r.available) == ("Bolsa CK Pequeña", 200, None, True)
    assert [v.variant_id for v in variants(ck, "bolsa_precio_normal.json", BOLSA)] == [""]


def test_urls():
    check_urls(ck, SLIP_SLUG, "calvinchile")
