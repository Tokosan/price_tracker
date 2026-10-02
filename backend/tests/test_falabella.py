import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.falabella import FalabellaProcessor

falabella = FalabellaProcessor()
BASE = "https://www.falabella.com/falabella-cl/product"
ZAPATILLA = f"{BASE}/143441472/zapatilla-urbana-mujer-blanco-ginevra-chinitown"


def parse(fixture, url):
    return falabella.parse(fixture_text("falabella", fixture), falabella.normalize(url))


def test_en_stock():
    r = parse("en_stock.json", f"{BASE}/80734737/baby-brezza/80734737")
    assert r.title.startswith("Baby Brezza Formula Pro Advanced")
    assert (r.price, r.list_price, r.currency, r.available) == (299990, None, "CLP", True)
    assert r.image_url == "https://media.falabella.com/falabellaCL/80734737_1/public"


def test_descuento_ignora_cmr():
    # cmrPrice 409.990, internetPrice 419.990, normalPrice tachado 629.990.
    r = parse("descuento_cmr.json", f"{BASE}/80758957")
    assert r.title == '55" Mini LED M70H 4K Samsung Vision AI Smart TV (2026)'
    assert (r.price, r.list_price, r.available) == (419990, 629990, True)


def test_talla_en_stock_usa_precio_de_evento():
    r = parse("tallas.json", f"{ZAPATILLA}/143441498")
    assert r.title == "Zapatilla Urbana Mujer Blanco Ginevra Chinitown (Blanco · 39)"
    assert (r.price, r.list_price, r.available) == (17990, 32990, True)
    assert r.image_url == "https://media.falabella.com/falabellaCL/143441498_01/public"


def test_talla_agotada_de_un_producto_con_stock():
    r = parse("tallas.json", f"{ZAPATILLA}/143441497")
    assert (r.price, r.list_price, r.available) == (17990, 32990, False)


def test_sin_sku_sigue_la_variante_actual():
    r = parse("tallas.json", f"{BASE}/143441472")
    assert r.title.endswith("(Blanco · 35)")  # currentVariant = 143441473
    assert r.available is True


def test_sku_que_ya_no_esta_queda_agotado_sin_precio():
    r = parse("tallas.json", f"{ZAPATILLA}/999")
    assert (r.price, r.available) == (None, False)


def test_agotado_con_precio():
    r = parse("agotado.json", f"{BASE}/121181480/zapatilla-saucony/121181486")
    assert r.title.endswith("(Beige · 40)")
    assert (r.price, r.list_price, r.available) == (79990, None, False)


def test_agotado_sin_variantes_no_tiene_precio():
    r = parse("agotado_sin_variantes.json", f"{BASE}/139751658")
    assert r.title == "Polera Manga Larga Niño Spiderman Spider Gesto Rojo Marvel"
    assert (r.price, r.available) == (None, False)
    assert falabella.sold_out_without_price is True


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("no_encontrado.json", f"{BASE}/999999999")


def test_respuestas_raras_son_error_de_lectura():
    ref = falabella.normalize(f"{BASE}/1")
    with pytest.raises(FetchError):
        falabella.parse("<html>403</html>", ref)
    with pytest.raises(FetchError):
        falabella.parse(json.dumps({"responseType": "OTRA_COSA", "data": {}}), ref)
    sin_variantes = json.dumps({"data": {"id": "1", "name": "x", "variants": []}})
    with pytest.raises(FetchError):
        falabella.parse(sin_variantes, ref)
    # Con SKU tampoco: sin OUT_OF_STOCK, una respuesta sin variantes no es un agotado.
    with pytest.raises(FetchError):
        falabella.parse(sin_variantes, falabella.normalize(f"{BASE}/1/slug/2"))
    with pytest.raises(FetchError):
        falabella.parse(
            json.dumps({"data": {"id": "1", "name": "x"}}), falabella.normalize(f"{BASE}/1/slug/2")
        )


def test_variantes_sin_sku_fijan_el_sku_de_la_actual():
    raw = fixture_text("falabella", "tallas.json")
    ref = falabella.normalize(f"{BASE}/143441472")  # sin SKU: la actual es 143441473
    variants = falabella.parse_variants(raw, ref)
    assert len(variants) == 6
    current = variants[0]
    assert current.selected
    assert (current.url, current.variant_id) == (f"{ZAPATILLA}/143441473", "143441473")
    assert current.label == "Blanco · 35: $17.990"
    assert [v.variant_id for v in variants].count("143441473") == 1
    others = {v.variant_id: v for v in variants[1:]}
    assert others["143441497"].label == "Blanco · 40: $17.990 (agotada)"
    assert others["143441497"].url == f"{ZAPATILLA}/143441497"
    assert not any(v.selected for v in others.values())
    assert all(v.external_id == "143441472" for v in variants)
    # Cada URL de variante vuelve a la misma variante al normalizarla.
    for v in variants:
        assert falabella.normalize(v.url).variant_id == v.variant_id


def test_variantes_con_sku_marcan_esa():
    raw = fixture_text("falabella", "tallas.json")
    url = f"{ZAPATILLA}/143441497"
    variants = falabella.parse_variants(raw, falabella.normalize(url))
    assert [v.variant_id for v in variants if v.selected] == ["143441497"]
    assert variants[0].url == url
    assert [v.variant_id for v in variants].count("143441497") == 1


def test_variantes_con_sku_y_otro_slug_conservan_la_url_del_link():
    raw = fixture_text("falabella", "tallas.json")
    url = f"{BASE}/143441472/otro-slug/143441498"
    current = falabella.parse_variants(raw, falabella.normalize(url))[0]
    assert (current.url, current.variant_id, current.selected) == (url, "143441498", True)


def test_sku_ausente_con_out_of_stock_queda_agotado():
    r = parse("agotado.json", f"{BASE}/121181480/zapatilla-saucony/999")
    assert (r.price, r.available) == (None, False)


def test_producto_de_una_variante_no_ofrece_selector():
    raw = fixture_text("falabella", "en_stock.json")
    assert falabella.parse_variants(raw, falabella.normalize(f"{BASE}/80734737")) == []


@pytest.mark.parametrize(
    ("url", "pid", "sku", "canonical"),
    [
        (f"{BASE}/80758957", "80758957", "", f"{BASE}/80758957"),
        (f"{BASE}/80758957/", "80758957", "", f"{BASE}/80758957"),
        (f"{BASE}/80758957/tv-samsung", "80758957", "", f"{BASE}/80758957/tv-samsung"),
        (
            f"{ZAPATILLA}/143441497?kid=x&utm_source=y#top",
            "143441472",
            "143441497",
            f"{ZAPATILLA}/143441497",
        ),
        (
            "http://falabella.com/falabella-cl/product/80758957/Slug-Raro/80758957?x=1",
            "80758957",
            "80758957",
            f"{BASE}/80758957/Slug-Raro/80758957",
        ),
        (
            "HTTPS://WWW.FALABELLA.COM/FALABELLA-CL/PRODUCT/80758957",
            "80758957",
            "",
            f"{BASE}/80758957",
        ),
    ],
)
def test_normaliza_url(url, pid, sku, canonical):
    assert falabella.matches(url)
    ref = falabella.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (pid, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.falabella.com.evil.com/falabella-cl/product/80758957",
        "https://evilfalabella.com/falabella-cl/product/80758957",
        "https://www.falabella.com/falabella-cl/category/cat7190148/Smart-TV",
        "https://www.falabella.com/falabella-cl/search?Ntt=televisor",
        "https://www.falabella.com/falabella-cl/product/abc",
        "https://www.falabella.com/sodimac-cl/product/80758957",
        "https://www.falabella.com/falabella-cl",
    ],
)
def test_no_matchea(url):
    assert not falabella.matches(url)


def test_registrado():
    assert find_processor(f"{BASE}/80758957") is not None
    assert find_processor(f"{BASE}/80758957").name == "falabella"


async def test_fetch_pide_site_antes_que_product_id(monkeypatch):
    calls = []

    async def fake_get_text(url, *, params=None):
        calls.append((url, list(params.items())))
        return "{}"

    monkeypatch.setattr("tracker.processors.falabella_platform.get_text", fake_get_text)
    await falabella.fetch_raw(falabella.normalize(f"{ZAPATILLA}/143441497"))
    assert calls == [
        (
            "https://www.falabella.com/s/browse/v3/product/cl",
            [("site", "falabella-cl"), ("productId", "143441472")],
        )
    ]
