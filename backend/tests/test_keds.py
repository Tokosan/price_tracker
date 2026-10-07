import json

from tests.conftest import fixture_text
from tests.vtex_apparel_helpers import check_urls, labels, parse
from tracker.processors import PROCESSORS

keds = PROCESSORS["keds"]
SLUG = "zapatilla-mujer-kickstart-seasonal-s-keds-wf54682-boh"
KICKSTART = f"https://www.keds.cl/{SLUG}/p"


def test_precio_antes_es_una_formula_y_no_se_guarda():
    raw = fixture_text("keds", "kickstart_tallas_mixtas.json")
    offer = json.loads(raw)[0]["items"][1]["sellers"][0]["commertialOffer"]
    assert (offer["Price"], offer["ListPrice"]) == (11996, 29990)  # 2,5 × el precio
    assert not keds.supports_list_price
    r = parse(keds, "kickstart_tallas_mixtas.json", f"{KICKSTART}?skuId=3657988")
    assert r.title == "Zapatilla Kickstart Seasonal S (Talla 5.5)"
    assert (r.price, r.list_price, r.available) == (11996, None, True)


def test_tallas():
    assert labels(keds, "kickstart_tallas_mixtas.json", KICKSTART)[:3] == [
        "Talla 5: $11.996 (agotada)",
        "Talla 5.5: $11.996",
        "Talla 6: $11.996 (agotada)",
    ]


def test_urls():
    check_urls(keds, SLUG, "kedscl")
