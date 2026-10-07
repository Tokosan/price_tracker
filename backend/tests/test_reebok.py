from tests.vtex_apparel_helpers import check_urls, labels, parse, variants
from tracker.processors import PROCESSORS

reebok = PROCESSORS["reebok"]
CALZA_SLUG = "calzas-running-high-rise-full-length-tights-mujer-100241933"
CALZA = f"https://www.reebok.cl/{CALZA_SLUG}/p"
MOCHILA = "https://www.reebok.cl/mochila-training-rbk-restore-backpack-mujer-accb123/p"
CALCETINES = (
    "https://www.reebok.cl/calcetines-tobilleros-training-act-core-ankle-sock-3p-unisex-accs049/p"
)


def test_talla_en_oferta():
    r = parse(reebok, "calza_tallas_mixtas.json", f"{CALZA}?skuId=76799")
    assert r.title == "Calza larga Running | High Rise Full Length Tights | Mujer (Talla L)"
    assert (r.price, r.list_price, r.currency, r.available) == (21996, 54990, "CLP", True)
    assert r.image_url.startswith("https://reebokcl.vteximg.com.br/")


def test_talla_agotada_vuelve_al_precio_normal():
    r = parse(reebok, "calza_tallas_mixtas.json", f"{CALZA}?skuId=76798")
    assert (r.price, r.list_price, r.available) == (54990, None, False)


def test_selector_de_tallas():
    vs = variants(reebok, "calza_tallas_mixtas.json", CALZA)
    assert len(vs) == 21
    assert vs[0].selected and vs[0].url == f"{CALZA}?skuId=76798"
    assert [v.label for v in vs[:3]] == [
        "Talla XL/S: $54.990 (agotada)",
        "Talla L: $21.996",
        "Talla 2XS/S: $54.990 (agotada)",
    ]


def test_talla_unica_sin_selector():
    r = parse(reebok, "mochila_talla_unica.json", MOCHILA)
    assert r.title == "Mochila Training | Rbk Restore Backpack | Mujer"
    assert (r.price, r.list_price, r.available) == (15996, 39990, True)
    vs = variants(reebok, "mochila_talla_unica.json", f"{MOCHILA}?skuId=85155")
    assert [(v.url, v.variant_id, v.label) for v in vs] == [(MOCHILA, "", "Talla única")]


def test_precio_normal_sin_precio_antes():
    r = parse(reebok, "calcetines_precio_normal.json", f"{CALCETINES}?skuId=88520")
    assert (r.price, r.list_price, r.available) == (7990, None, True)
    assert labels(reebok, "calcetines_precio_normal.json", CALCETINES)[0] == (
        "Talla S: $7.990 (agotada)"
    )


def test_urls():
    check_urls(reebok, CALZA_SLUG, "reebokcl")
