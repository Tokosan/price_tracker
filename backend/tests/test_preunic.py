import asyncio
import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors import preunic as preunic_mod
from tracker.processors.preunic import PreunicProcessor

preunic = PreunicProcessor()
COTONITOS = "https://preunic.cl/products/cotonitos-de-algodon-270-unidades-nenito-s"


def url(slug):
    return f"https://preunic.cl/products/{slug}"


def parse(fixture, slug):
    return preunic.parse(fixture_text("preunic", fixture), preunic.normalize(url(slug)))


def _default_variant(data):
    vid = data["data"]["relationships"]["defaultVariant"]["data"]["id"]
    return next(x for x in data["included"] if x["type"] == "variant" and x["id"] == vid)


def test_en_stock():
    r = parse("cotonitos_en_stock.json", "cotonitos-de-algodon-270-unidades-nenito-s")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Cotonitos de Algodón 270 Unidades Nenito's",
        1599,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://static.preunic.cl/")


def test_precio_de_la_variante_y_no_el_del_producto():
    # El `price` del producto (1499) es el de la variante maestra; la ficha muestra 1599.
    data = json.loads(fixture_text("preunic", "cotonitos_en_stock.json"))
    assert data["data"]["attributes"]["price"] == "1499.0"
    assert _default_variant(data)["attributes"]["price"] == "1599.0"


def test_oferta_sin_tarjeta_y_sbpay_ignorado():
    raw = fixture_text("preunic", "toallitas_oferta_y_sbpay.json")
    attrs = _default_variant(json.loads(raw))["attributes"]
    assert (attrs["price"], attrs["offerPrice"], attrs["cardPrice"]) == ("2599.0", 2000, 1741)
    r = preunic.parse(
        raw, preunic.normalize(url("pack-de-toallitas-humedas-para-bebe-160-unidades"))
    )
    assert (r.price, r.list_price, r.available) == (2000, 2599, True)


@pytest.mark.parametrize(
    ("fixture", "slug", "price", "list_price"),
    [
        ("enjuague_agotado.json", "enjuague-bucal", 1999, None),
        ("babero_agotado_con_oferta.json", "nenitos-babero-de-algodon", 2374, 2499),
    ],
)
def test_agotado_conserva_el_precio(fixture, slug, price, list_price):
    attrs = _default_variant(json.loads(fixture_text("preunic", fixture)))["attributes"]
    assert (attrs["storeExclusive"], attrs["communes"], attrs["zones"]) == (False, [], [])
    r = parse(fixture, slug)
    assert (r.price, r.list_price, r.available) == (price, list_price, False)


def test_disponible_por_la_zona_de_santiago():
    # La comuna 340 (Santiago) no está en `communes`, pero la zona 39 sí está en `zones`.
    raw = fixture_text("preunic", "pistola_solo_zona.json")
    attrs = _default_variant(json.loads(raw))["attributes"]
    assert 340 not in attrs["communes"] and 39 in attrs["zones"]
    r = preunic.parse(raw, preunic.normalize(url("pistola-de-silicona")))
    assert (r.price, r.list_price, r.available) == (5224, 5499, True)


def test_sin_stock_en_santiago_es_agotado():
    # Se vende en otras comunas, pero no en la comuna por defecto de la ficha.
    raw = fixture_text("preunic", "block_sin_stock_en_santiago.json")
    attrs = _default_variant(json.loads(raw))["attributes"]
    assert attrs["storeExclusive"] and attrs["purchasable"]
    assert 340 not in attrs["communes"] and 39 not in attrs["zones"]
    r = preunic.parse(
        raw, preunic.normalize(url("block-con-hojas-tamano-carta-prepicado-80-hojas"))
    )
    assert (r.price, r.available) == (2374, False)


def test_no_exclusivo_con_in_stock_esta_disponible():
    # Caso armado: ningún producto muestreado trae inStock en true.
    data = json.loads(fixture_text("preunic", "enjuague_agotado.json"))
    _default_variant(data)["attributes"]["inStock"] = True
    r = preunic.parse(json.dumps(data), preunic.normalize(url("enjuague-bucal")))
    assert r.available is True


def test_lee_la_variante_por_defecto():
    raw = fixture_text("preunic", "coloracion_dos_variantes.json")
    data = json.loads(raw)
    assert len(data["data"]["relationships"]["variants"]["data"]) == 2
    assert _default_variant(data)["attributes"]["sku"] == "2011864"
    r = preunic.parse(raw, preunic.normalize(url("coloracion-creme-gloss-300-castano-oscuro")))
    assert (r.price, r.available) == (7699, True)
    # Si la variante por defecto pasa a ser la otra, se lee esa.
    other = next(
        x
        for x in data["included"]
        if x["type"] == "variant" and x["attributes"]["sku"] == "2011861"
    )
    other["attributes"]["offerPrice"] = 6000
    data["data"]["relationships"]["defaultVariant"]["data"]["id"] = other["id"]
    r = preunic.parse(
        json.dumps(data), preunic.normalize(url("coloracion-creme-gloss-300-castano-oscuro"))
    )
    assert (r.price, r.list_price) == (6000, 7699)


def test_oferta_igual_al_precio_no_es_descuento():
    r = parse("cotonitos_en_stock.json", "cotonitos-de-algodon-270-unidades-nenito-s")
    assert r.list_price is None


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json", "no-existe-este-producto")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.pop("communes"),
        lambda a: a.pop("zones"),
        lambda a: a.pop("storeExclusive"),
        lambda a: a.update(inStock=None),
    ],
)
def test_sin_datos_de_stock_es_error_de_lectura(mutate):
    data = json.loads(fixture_text("preunic", "cotonitos_en_stock.json"))
    mutate(_default_variant(data)["attributes"])
    with pytest.raises(FetchError):
        preunic.parse(json.dumps(data), preunic.normalize(COTONITOS))


def test_sin_variante_por_defecto_es_error_de_lectura():
    data = json.loads(fixture_text("preunic", "cotonitos_en_stock.json"))
    data["included"] = [x for x in data["included"] if x["type"] != "variant"]
    with pytest.raises(FetchError):
        preunic.parse(json.dumps(data), preunic.normalize(COTONITOS))


def test_precio_roto_queda_en_none():
    data = json.loads(fixture_text("preunic", "cotonitos_en_stock.json"))
    _default_variant(data)["attributes"].update(price="0.0", offerPrice=None)
    r = preunic.parse(json.dumps(data), preunic.normalize(COTONITOS))
    assert r.price is None


@pytest.mark.parametrize("raw", ["<html>error</html>", "[]", '{"data": null}'])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError):
        preunic.parse(raw, preunic.normalize(COTONITOS))


def test_pide_la_api_del_bff(monkeypatch):
    calls = []

    async def fake_get_text(url, **kwargs):
        calls.append((url, kwargs))
        return "{}"

    monkeypatch.setattr(preunic_mod, "get_text", fake_get_text)
    asyncio.run(preunic.fetch_raw(preunic.normalize(COTONITOS)))
    [(api, kwargs)] = calls
    assert api == (
        "https://api.preunic.cl/bff-pu-ecommerce/bff/spr/products/"
        "cotonitos-de-algodon-270-unidades-nenito-s"
    )
    assert kwargs["params"]["include"] == "variants,images,product_properties,taxons"
    assert kwargs["params"]["api-key"]
    # Sin Origin el BFF responde 403.
    assert kwargs["headers"]["Origin"] == "https://preunic.cl"


def test_sin_variantes():
    assert preunic.supports_variants is False
    assert preunic.parse_variants("{}", preunic.normalize(COTONITOS)) == []


@pytest.mark.parametrize(
    "u",
    [
        COTONITOS,
        "https://www.preunic.cl/products/cotonitos-de-algodon-270-unidades-nenito-s",
        "http://preunic.cl/products/cotonitos-de-algodon-270-unidades-nenito-s/",
        "https://PREUNIC.CL/products/Cotonitos-De-Algodon-270-Unidades-Nenito-S?from=home#x",
        "https://preunic.cl/products/cotonitos-de-algodon-270-unidades-nenito-s?source=search",
    ],
)
def test_normaliza_url(u):
    assert preunic.normalize(u) == ProductRef(
        "cotonitos-de-algodon-270-unidades-nenito-s", COTONITOS
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(COTONITOS).name == "preunic"
    for u in [
        "https://preunic.cl/",
        "https://preunic.cl/products",
        "https://preunic.cl/products/",
        "https://preunic.cl/t/mi-bebe/higiene-infantil",
        "https://preunic.cl/campaigns/cyber",
        "https://preunic.cl/landings/maquillaje",
        "https://preunic.cl/products/cotonitos/extra",
        "https://preunic.cl/products/coto_nitos",
        "https://preunic.cl.evil.com/products/cotonitos",
        "https://evilpreunic.cl/products/cotonitos",
        "https://salcobrand.cl/products/cotonitos",
        "javascript://preunic.cl/products/cotonitos",
    ]:
        assert not preunic.matches(u), u
