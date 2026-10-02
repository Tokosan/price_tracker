import asyncio
import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors import woocommerce as woo_mod
from tracker.processors.ecofarmacias import EcofarmaciasProcessor
from tracker.rules import Reading, check_anomaly

eco = EcofarmaciasProcessor()
BASE = "https://www.ecofarmacias.cl/producto"
ENSURE = f"{BASE}/ensure-advance-chocolate-850-g/"
BAODA_SLUG = "baoda-mamadera-con-chupete-de-silicona-240-ml"
BAODA = f"{BASE}/{BAODA_SLUG}/"
COPA_SLUG = "copa-menstrual-bentley-certificada-reutilizable-talla-a-eleccion-s-xs-l"
COPA = f"{BASE}/{COPA_SLUG}/"
VOGUE = f"{BASE}/vogue-base-liquida-fps-15-resist-30-ml/"


def parse(fixture, url):
    return eco.parse(fixture_text("ecofarmacias", fixture), eco.normalize(url))


def variants(fixture, url):
    return eco.parse_variants(fixture_text("ecofarmacias", fixture), eco.normalize(url))


def test_en_stock():
    r = parse("en_stock_ensure.json", ENSURE)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Ensure Advance Chocolate 850 g (Abbott)",
        23690,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://www.ecofarmacias.cl/wp-content/uploads/")


def test_descuento_trae_precio_antes():
    r = parse(
        "descuento_kotex.json",
        f"{BASE}/kotex-tampones-con-aplicador-medio-x-8-tampones-descuentos/",
    )
    assert r.title == "Kotex Tampones con aplicador medio x 8 tampones DESCUENTOS"
    assert (r.price, r.list_price, r.available) == (2000, 2980, True)


def test_agotado_con_precio():
    r = parse("agotado_axe.json", f"{BASE}/axe-desodorante-aerosol-apollo-152-ml/")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Axe Desodorante Aerosol Apollo 152 ml",
        2990,
        None,
        False,
    )


def test_producto_simple_no_ofrece_variantes():
    assert variants("en_stock_ensure.json", ENSURE) == []


def test_producto_simple_con_seleccion_no_existe():
    with pytest.raises(NotFoundError):
        parse("en_stock_ensure.json", f"{ENSURE}?attribute_color=ROJO")


def test_sin_seleccion_sigue_la_primera_variacion():
    r = parse("variable_baoda.json", BAODA)
    assert r.title == "Baoda Mamadera con Chupete de Silicona 240 Ml (NIÑO)"
    assert (r.price, r.list_price, r.available) == (1990, None, True)


def test_seleccion_elige_la_variacion():
    r = parse("variable_baoda.json", f"{BAODA}?attribute_color=NI%C3%91A")
    assert r.title.endswith("(NIÑA)")
    # Sin distinguir mayúsculas ni tildes, como la ficha.
    assert parse("variable_baoda.json", f"{BAODA}?attribute_COLOR=nina").title.endswith("(NIÑA)")


def test_variacion_que_ya_no_existe():
    with pytest.raises(NotFoundError):
        parse("variable_baoda.json", f"{BAODA}?attribute_color=AZUL")


def test_selector_de_variantes():
    vs = variants("variable_baoda.json", BAODA)
    assert [(v.label, v.selected) for v in vs] == [("NIÑO: $1.990", True), ("NIÑA: $1.990", False)]
    # Sin selección en el link, la actual también se devuelve con la suya: queda fija.
    assert vs[0].url == f"{BAODA}?attribute_color=NI%C3%91O"
    for v in vs:
        assert v.external_id == BAODA_SLUG
        assert eco.normalize(v.url) == ProductRef(BAODA_SLUG, v.url, v.variant_id)
        assert eco.variant_label(v.external_id, v.variant_id) == v.label.split(":")[0]


def test_variaciones_con_precio_distinto_y_agotadas():
    url = f"{COPA}?attribute_talla=L"
    r = parse("variable_copa_agotada.json", url)
    assert (r.price, r.available) == (9800, False)
    vs = variants("variable_copa_agotada.json", url)
    assert vs[0].selected and vs[0].url == url
    assert [v.label for v in vs] == [
        "L: $9.800 (agotada)",
        "S: $7.950 (agotada)",
        "XS: $9.980 (agotada)",
    ]
    assert parse("variable_copa_agotada.json", f"{COPA}?attribute_talla=S").price == 7950


def test_stock_del_padre_no_cuenta():
    # El padre dice is_in_stock=true, pero todas sus variaciones están agotadas (la ficha
    # muestra "Agotado").
    data = json.loads(fixture_text("ecofarmacias", "variable_vogue_padre_en_stock.json"))
    assert data["products"][0]["is_in_stock"] is True
    r = parse("variable_vogue_padre_en_stock.json", VOGUE)
    assert (r.title, r.price, r.available) == (
        "Vogue Base Líquida FPS 15 Resist 30 ml (MIEL)",
        4390,
        False,
    )


def test_una_sola_variacion_se_ofrece_sin_seleccion():
    data = json.loads(fixture_text("ecofarmacias", "variable_baoda.json"))
    data["products"][0]["variations"] = data["products"][0]["variations"][:1]
    vs = eco.parse_variants(json.dumps(data), eco.normalize(f"{BAODA}?attribute_color=NI%C3%91O"))
    assert [(v.url, v.variant_id, v.selected) for v in vs] == [(BAODA, "", True)]
    r = eco.parse(json.dumps(data), eco.normalize(BAODA))
    assert r.title == "Baoda Mamadera con Chupete de Silicona 240 Ml"


def test_variable_sin_variaciones_es_error_de_lectura():
    data = json.loads(fixture_text("ecofarmacias", "variable_baoda.json"))
    data["variations"] = []
    with pytest.raises(FetchError):
        eco.parse(json.dumps(data), eco.normalize(BAODA))


def test_no_existe():
    # La Store API responde [] (HTTP 200) para un slug inexistente.
    raw = json.dumps({"products": [], "variations": []})
    with pytest.raises(NotFoundError):
        eco.parse(raw, eco.normalize(f"{BASE}/no-existe-este-producto/"))


def test_producto_en_la_papelera_no_existe():
    ref = eco.normalize(f"{BASE}/__trashed-3/")
    with pytest.raises(NotFoundError):
        asyncio.run(eco.fetch_raw(ref))
    with pytest.raises(NotFoundError):
        eco.parse(fixture_text("ecofarmacias", "en_stock_ensure.json"), ref)


def test_respuesta_que_no_es_json():
    with pytest.raises(FetchError):
        eco.parse("<html>mantención</html>", eco.normalize(ENSURE))


def test_agotado_con_precio_0_no_es_anomalia():
    data = json.loads(fixture_text("ecofarmacias", "agotado_axe.json"))
    data["products"][0]["prices"]["price"] = "0"
    r = eco.parse(json.dumps(data), eco.normalize(ENSURE))
    assert (r.price, r.available) == (None, False)
    reading = Reading(price=None, list_price=None, available=False)
    assert check_anomaly(reading, 2990, eco.anomaly_drop_pct, eco.sold_out_without_price) is None


def test_respeta_currency_minor_unit():
    data = json.loads(fixture_text("ecofarmacias", "descuento_kotex.json"))
    prices = data["products"][0]["prices"]
    prices.update(price="200000", regular_price="298000", currency_minor_unit=2)
    r = eco.parse(json.dumps(data), eco.normalize(ENSURE))
    assert (r.price, r.list_price) == (2000, 2980)


def test_fetch_raw_junta_producto_y_variaciones(monkeypatch):
    product = json.loads(fixture_text("ecofarmacias", "variable_baoda.json"))
    calls = []

    async def fake_get_text(url, *, params=None, **kw):
        calls.append(params)
        key = "variations" if params.get("type") == "variation" else "products"
        return json.dumps(product[key])

    monkeypatch.setattr(woo_mod, "get_text", fake_get_text)
    raw = asyncio.run(eco.fetch_raw(eco.normalize(BAODA)))
    assert json.loads(raw) == product
    assert calls == [
        {"slug": BAODA_SLUG},
        {"type": "variation", "include": "127514,127515", "per_page": "100"},
    ]


@pytest.mark.parametrize(
    ("url", "selection"),
    [
        (ENSURE, ""),
        ("https://ecofarmacias.cl/producto/ensure-advance-chocolate-850-g", ""),
        ("http://www.ecofarmacias.cl/producto/Ensure-Advance-Chocolate-850-G/?utm_source=x#a", ""),
        (f"{ENSURE}?attribute_color=", ""),
        (f"{ENSURE}?attribute_color=NI%C3%91A&utm_source=x", "color=NI%C3%91A"),
        (f"{ENSURE}?attribute_talla=S&attribute_color=ROJO", "color=ROJO&talla=S"),
    ],
)
def test_normaliza_url(url, selection):
    ref = eco.normalize(url)
    assert ref.external_id == "ensure-advance-chocolate-850-g"
    assert ref.variant_id == selection
    query = "&".join(f"attribute_{p}" for p in selection.split("&")) if selection else ""
    assert ref.canonical_url == ENSURE + (f"?{query}" if query else "")


def test_matchea_solo_fichas_de_su_dominio():
    assert eco.domain() == "www.ecofarmacias.cl"
    assert find_processor(ENSURE).name == "ecofarmacias"
    assert not eco.matches("https://www.ecofarmacias.cl/")
    assert not eco.matches("https://www.ecofarmacias.cl/categoria-producto/medicamentos/")
    assert not eco.matches("https://www.ecofarmacias.cl/producto/")
    assert not eco.matches("https://www.ecofarmacias.cl/?s=ensure&post_type=product")
    assert not eco.matches("https://www.ecofarmacias.cl/producto/ensure/otra-cosa/")
    assert not eco.matches("https://www.ecofarmacias.cl.evil.com/producto/ensure/")
    assert not eco.matches("https://wwwecofarmacias.cl/producto/ensure/")
    assert not eco.matches("https://evilecofarmacias.cl/producto/ensure/")
