"""Casaideas: respuestas reales del GraphQL de Magento (`route`, headless.casaideas.cl)."""

import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.casaideas import CasaideasProcessor

ci = CasaideasProcessor()
P = "https://www.casaideas.cl/producto"
BOWL = f"{P}/3228759000011-bowl-con-division-para-salsa.html"
CUADERNO = f"{P}/3205806000460-cuaderno-1-2-oficio.html"
TOPPER = f"{P}/c000000000053-topper-de-cama-memory-gel.html"
COBERTOR = f"{P}/c000000000342-cobertor-cordero-con-estampado.html"


def parse(fixture, url):
    return ci.parse(fixture_text("casaideas", fixture), ci.normalize(url))


def test_descuento():
    r = parse("descuento_bowl.json", BOWL)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Bowl con división para salsa",
        6490,
        12990,
        "CLP",
        True,
    )
    assert r.image_url == (
        "https://headless.casaideas.cl/media/catalog/product/3/2/3228759000011_1_4.jpg"
    )
    assert (
        ci.parse_variants(fixture_text("casaideas", "descuento_bowl.json"), ci.normalize(BOWL))
        == []
    )


def test_agotado_oculto_conserva_precio():
    # La ficha de Next.js da 404 y `products` no lo lista, pero `route` sí lo devuelve.
    r = parse("agotado_oculto_cuaderno.json", CUADERNO)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Cuaderno 1/2 Oficio",
        3590,
        6990,
        False,
    )


def test_cualquier_talla_y_talla_puntual():
    r = parse("tallas_topper.json", TOPPER)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Topper de cama memory gel",
        62990,
        None,
        True,
    )
    r = parse("tallas_topper.json", f"{TOPPER}?sku=3227607000012")
    assert (r.title, r.price, r.available) == (
        "Topper de cama memory gel (talla King)",
        94990,
        True,
    )
    # Una talla que ya no viene en `variants` está agotada.
    r = parse("tallas_topper.json", f"{TOPPER}?sku=3227607000099")
    assert (r.price, r.list_price, r.available) == (None, None, False)


def test_variantes():
    raw = fixture_text("casaideas", "tallas_topper.json")
    variants = ci.parse_variants(raw, ci.normalize(TOPPER))
    assert [v.label for v in variants] == [
        "Cualquier talla",
        "Talla 2 Plazas: $82.990",
        "Talla King: $94.990",
        "Talla 1.5 Plaza: $62.990",
    ]
    assert variants[0].selected and variants[0].variant_id == ""
    assert variants[2].url == f"{TOPPER}?sku=3227607000012"
    selected = ci.parse_variants(raw, ci.normalize(f"{TOPPER}?sku=3227607000012"))
    assert selected[0].label == "Talla King: $94.990" and selected[0].selected


def test_una_sola_talla_con_stock_no_ofrece_variantes():
    raw = fixture_text("casaideas", "una_talla_cobertor.json")
    assert ci.parse_variants(raw, ci.normalize(COBERTOR)) == []
    r = parse("una_talla_cobertor.json", COBERTOR)
    assert (r.price, r.list_price, r.available) == (24390, 34990, True)


def _edit(fixture, **fields):
    body = json.loads(fixture_text("casaideas", fixture))
    body["data"]["route"].update(fields)
    return json.dumps(body)


def test_configurable_agotado():
    raw = _edit("tallas_topper.json", stock_status="OUT_OF_STOCK", variants=[])
    r = ci.parse(raw, ci.normalize(TOPPER))
    assert (r.price, r.available) == (62990, False)
    assert ci.parse_variants(raw, ci.normalize(TOPPER)) == []


def test_sin_precio_con_stock_es_error():
    raw = _edit("descuento_bowl.json", price_range=None)
    with pytest.raises(FetchError):
        ci.parse(raw, ci.normalize(BOWL))
    raw = _edit("descuento_bowl.json", price_range=None, stock_status="OUT_OF_STOCK")
    r = ci.parse(raw, ci.normalize(BOWL))
    assert (r.price, r.available) == (None, False)


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json", BOWL)


def test_no_es_producto():
    raw = json.dumps({"data": {"route": {"__typename": "CategoryTree"}}})
    with pytest.raises(NotFoundError):
        ci.parse(raw, ci.normalize(BOWL))


@pytest.mark.parametrize(
    "raw",
    ["<html>", '{"errors": [{"message": "x"}]}', '{"data": {}}', "[]"],
)
def test_respuesta_rota(raw):
    with pytest.raises(FetchError):
        ci.parse(raw, ci.normalize(BOWL))


@pytest.mark.parametrize(
    "url",
    [
        "https://www.casaideas.cl.evil.com/producto/3228759000011-bowl.html",
        "https://evilcasaideas.cl/producto/3228759000011-bowl.html",
        "https://www.casaideas.com.pe/producto/3228759000011-bowl.html",
        "https://www.casaideas.cl/categoria/productos/ofertas",
        "https://www.casaideas.cl/contenido/clp-cocina",
        "https://www.casaideas.cl/producto/a/b.html",
    ],
)
def test_no_matchea(url):
    assert not ci.matches(url)


def test_normaliza():
    ref = ci.normalize(
        "http://casaideas.cl/producto/C000000000053-Topper-de-cama-memory-gel.html?sku=3227607000012#x"
    )
    assert ref.external_id == "c000000000053-topper-de-cama-memory-gel"
    assert ref.variant_id == "3227607000012"
    assert ref.canonical_url == f"{TOPPER}?sku=3227607000012"
    assert ci.normalize(f"{BOWL}?sku=<script>").variant_id == ""


def test_registrado():
    assert find_processor(BOWL).name == "casaideas"
