import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, Variant, find_processor
from tracker.processors.paris import ParisProcessor

paris = ParisProcessor()
ZAPATILLA = (
    "https://www.paris.cl/zapatilla-urbana-basket-clasica-court-vision-low-hombre-855637.html"
)
RACK = "https://www.paris.cl/rack-tv-65-elegant-394782.html"
FUNDA = "https://www.paris.cl/funda-de-plumon-king-lino-408657.html"


def parse(fixture, url):
    return paris.parse(fixture_text("paris", fixture), paris.normalize(url))


def test_talla_con_oferta():
    r = parse("tallas.json", f"{ZAPATILLA}?sku=855637004")
    assert r.title == "Zapatilla Urbana Basket Clásica Court Vision Low Hombre (CL 40)"
    assert (r.price, r.list_price, r.currency, r.available) == (49990, 74990, "CLP", True)
    assert r.image_url.startswith("https://cl-dam-resizer.ecomm.cencosud.com/")


def test_descuento_ignora_tarjeta_cencosud():
    # regular 249.990, offer 149.990, paymentMethod (cencosudCard) 124.990.
    r = parse("descuento_tarjeta.json", RACK)
    assert r.title == 'Rack Tv 65" Elegant (Negro)'  # sin SKU: la masterVariant
    assert (r.price, r.list_price, r.available) == (149990, 249990, True)


def test_marketplace():
    r = parse("marketplace.json", "https://www.paris.cl/panel-bento-light-60-MKTDEDRP8J.html")
    assert r.title == 'Panel Bento Light 60"'  # una sola variante: sin etiqueta
    assert (r.price, r.list_price, r.available) == (99990, 149990, True)


def test_agotado_sin_oferta():
    r = parse(
        "agotado.json",
        "https://www.paris.cl/perfume-ralph-lauren-polo-sport-hombre-edt-118-ml-851815.html",
    )
    assert r.title == "Perfume Ralph Lauren Polo Sport Hombre EDT 118 ml"
    assert (r.price, r.list_price, r.available) == (132990, None, False)


@pytest.mark.parametrize(
    ("sku", "color", "available"),
    [("408657005", "Verde", False), ("408657006", "Marengo", False), ("408657009", "Blanco", True)],
)
def test_stock_por_color(sku, color, available):
    r = parse("colores_mixtos.json", f"{FUNDA}?sku={sku}")
    assert r.title == f"Funda de Plumón King Lino ({color})"
    assert (r.price, r.list_price, r.available) == (111990, 139990, available)


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("no_encontrado.json", "https://www.paris.cl/no-existe-NOEXISTE999.html")


def test_sku_que_ya_no_esta_es_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("tallas.json", f"{ZAPATILLA}?sku=855637999")


def test_respuestas_raras_son_error_de_lectura():
    ref = paris.normalize(RACK)
    body = json.loads(fixture_text("paris", "descuento_tarjeta.json"))
    with pytest.raises(FetchError):
        paris.parse("<html>", ref)
    with pytest.raises(FetchError):
        paris.parse(json.dumps({**body, "serviceability": None}), ref)
    with pytest.raises(FetchError):  # sin el stock del SKU no se sabe si está agotado
        paris.parse(json.dumps({**body, "serviceability": {"itemsServiceability": []}}), ref)
    product = {**body["product"]}
    del product["masterVariant"]
    with pytest.raises(FetchError):
        paris.parse(json.dumps({**body, "product": product}), ref)


def test_variantes_por_talla():
    raw = fixture_text("paris", "tallas.json")
    url = f"{ZAPATILLA}?sku=855637004"
    variants = paris.parse_variants(raw, paris.normalize(url))
    assert len(variants) == 10
    assert (variants[0].url, variants[0].variant_id, variants[0].selected) == (
        url,
        "855637004",
        True,
    )
    assert variants[0].label == "CL 40: $49.990"
    assert sum(v.selected for v in variants) == 1
    for v in variants:
        assert v.external_id == "855637"
        assert paris.normalize(v.url).variant_id == v.variant_id


def test_variantes_sin_sku_fijan_el_de_la_master():
    raw = fixture_text("paris", "colores_mixtos.json")
    variants = paris.parse_variants(raw, paris.normalize(FUNDA))
    current = variants[0]
    assert current.selected
    assert (current.url, current.variant_id) == (f"{FUNDA}?sku=408657005", "408657005")
    labels = {v.variant_id: v.label for v in variants}
    assert labels["408657005"] == "Verde: $111.990 (agotada)"
    assert labels["408657009"] == "Blanco: $111.990"


PANEL = "https://www.paris.cl/panel-bento-light-60-MKTDEDRP8J.html"


@pytest.mark.parametrize("url", [PANEL, f"{PANEL}?sku=MKTDEDRP8J-1"])
def test_una_variante_se_ofrece_sin_sku(url):
    # Con o sin ?sku= se agrega el mismo Product (variant_id vacío).
    raw = fixture_text("paris", "marketplace.json")
    assert paris.parse_variants(raw, paris.normalize(url)) == [
        Variant(PANEL, "", "MKTDEDRP8J", "", True)
    ]
    r = paris.parse(raw, paris.normalize(url))
    assert (r.price, r.available) == (99990, True)


def test_una_variante_con_otro_sku_es_no_encontrado():
    raw = fixture_text("paris", "marketplace.json")
    with pytest.raises(NotFoundError):
        paris.parse_variants(raw, paris.normalize(f"{PANEL}?sku=MKTDEDRP8J-9"))


@pytest.mark.parametrize(
    ("url", "key", "sku", "canonical"),
    [
        (RACK, "394782", "", RACK),
        (f"{RACK}?cgid=muebles&utm_source=x#top", "394782", "", RACK),
        (f"{RACK}?sku=394782003&cgid=x", "394782", "394782003", f"{RACK}?sku=394782003"),
        ("http://paris.cl/rack-tv-65-elegant-394782.html", "394782", "", RACK),
        ("HTTPS://WWW.PARIS.CL/rack-tv-65-elegant-394782.html", "394782", "", RACK),
        (
            "https://www.paris.cl/panel-bento-light-60-MKTDEDRP8J.html?sku=MKTDEDRP8J-1",
            "MKTDEDRP8J",
            "MKTDEDRP8J-1",
            "https://www.paris.cl/panel-bento-light-60-MKTDEDRP8J.html?sku=MKTDEDRP8J-1",
        ),
        (f"{RACK}?sku=<script>", "394782", "", RACK),
    ],
)
def test_normaliza_url(url, key, sku, canonical):
    assert paris.matches(url)
    ref = paris.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (key, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.paris.cl.evil.com/rack-tv-65-elegant-394782.html",
        "https://evilparis.cl/rack-tv-65-elegant-394782.html",
        "https://www.paris.cl/hombre/ofertas/",
        "https://www.paris.cl/tecnologia/televisores/",
        "https://www.paris.cl/search?q=rack",
        "https://www.paris.cl/muebles/rack-tv-65-elegant-394782.html",
        "https://www.paris.cl/394782.html",
    ],
)
def test_no_matchea(url):
    assert not paris.matches(url)


def test_registrado():
    assert find_processor(RACK).name == "paris"


async def test_fetch_pide_producto_y_stock_de_todos_los_skus(monkeypatch):
    body = json.loads(fixture_text("paris", "colores_mixtos.json"))
    calls = []

    async def fake_get_text(url, *, params=None):
        calls.append((url, params))
        part = "product" if "/by-key/" in url else "serviceability"
        return json.dumps(body[part])

    monkeypatch.setattr("tracker.processors.paris.get_text", fake_get_text)
    raw = await paris.fetch_raw(paris.normalize(f"{FUNDA}?sku=408657009"))
    base = "https://be-paris-backend-cl-ms-api.ccom.paris.cl/products"
    assert calls == [
        (f"{base}/by-key/408657", None),
        (
            f"{base}/serviceability/by-skus",
            {
                "skusList": "408657005,408657006,408657007,408657008,408657009",
                "locality": "13114",
            },
        ),
    ]
    assert paris.parse(raw, paris.normalize(f"{FUNDA}?sku=408657009")).available is True
