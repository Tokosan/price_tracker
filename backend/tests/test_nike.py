from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

nike = PROCESSORS["nike"]
SLUG = "hq3950-002-air-jordan-mvp-92"
JORDAN = f"https://www.nike.cl/{SLUG}/p"
SHOX = "https://www.nike.cl/av3595-002-nike-shox-tl-1/p"


def test_descuento_y_tallas_sin_color():
    # Los items traen `talle` y `color` ("Negro."); el color es el mismo en toda la ficha.
    r = parse(nike, "jordan_mvp_descuento.json", JORDAN)
    assert r.title == "Air Jordan MVP 92 (Talla H 7 / M 8.5)"
    assert (r.price, r.list_price, r.available) == (107990, 152990, True)
    assert r.image_url.startswith("https://nikeclprod.vteximg.com.br/")
    assert labels(nike, "jordan_mvp_descuento.json", JORDAN)[:2] == [
        "Talla H 7 / M 8.5: $107.990",
        "Talla H 7.5 / M 9: $107.990",
    ]


def test_precio_normal_y_tallas_agotadas():
    r = parse(nike, "shox_precio_normal.json", f"{SHOX}?skuId=152406")
    assert r.title == "Nike Shox TL (Talla H 7.5 / M 9)"
    assert (r.price, r.list_price, r.available) == (192990, None, True)
    agotada = parse(nike, "shox_precio_normal.json", SHOX)
    assert (agotada.price, agotada.available) == (192990, False)


def test_slug_con_espacio_duro():
    url = "https://www.nike.cl/if1610-003-luka%C2%A077/p"
    assert nike.normalize(url).external_id == "if1610-003-luka\xa077"


def test_urls():
    # La API se lee por la cuenta `nikeclprod`, sin pasar por el Cloudflare de www.nike.cl.
    check_urls(nike, SLUG, "nikeclprod")
