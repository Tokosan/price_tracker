from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

trial = PROCESSORS["trial"]
TRAJE_SLUG = "traje-hombre-formal-regular-executive-azul-marino-1550256981"
TRAJE = f"https://www.trial.cl/{TRAJE_SLUG}/p"
CAMISA = "https://www.trial.cl/camisa-lino-algodon-braulio-blanco-1131216405/p"


def test_rebaja_en_el_precio_y_normal_en_list_price():
    # En Trial `PriceWithoutDiscount` = `Price`; el precio normal solo viene en `ListPrice`.
    r = parse(trial, "camisa_descuento.json", CAMISA)
    assert r.title == "Camisa Lino Algodón Braulio Blanco (Talla XXL)"
    assert (r.price, r.list_price, r.available) == (19990, 49990, True)


def test_talla_agotada_conserva_precio_y_precio_antes():
    r = parse(trial, "traje_tallas_mixtas.json", TRAJE)
    assert (r.price, r.list_price, r.available) == (149990, 199990, False)
    r = parse(trial, "traje_tallas_mixtas.json", f"{TRAJE}?skuId=33637")
    assert r.title.endswith("(Talla 50)")
    assert (r.price, r.list_price, r.available) == (149990, 199990, True)
    assert len(labels(trial, "traje_tallas_mixtas.json", TRAJE)) == 24


def test_urls():
    check_urls(trial, TRAJE_SLUG, "trialcl")
