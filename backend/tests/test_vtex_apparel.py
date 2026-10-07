"""Base de las tiendas de ropa en VTEX: etiquetas de talla/color, respaldo por pagetype y
precio "antes" desactivable. Cada tienda tiene además su propio test."""

import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import PROCESSORS, NotFoundError, vtex
from tracker.processors.jumbo import JumboProcessor
from tracker.processors.vtex_apparel import VtexApparelProcessor

APPAREL = [
    "reebok",
    "levis",
    "tommy",
    "calvinklein",
    "americaneagle",
    "trial",
    "ellus",
    "keds",
    "colloky",
    "ferouch",
    "caffarena",
    "opaline",
    "nike",
]


class Tienda(VtexApparelProcessor):
    name = "tienda"
    label = "Tienda"
    host = "www.tienda.cl"
    account = "tiendacl"


tienda = Tienda()


def _item(item_id, **attrs):
    return {"itemId": item_id, "variations": list(attrs), **{k: [v] for k, v in attrs.items()}}


def test_todas_registradas_con_selector_de_tallas():
    for name in APPAREL:
        proc = PROCESSORS[name]
        assert isinstance(proc, VtexApparelProcessor)
        assert proc.supports_variants and proc.pagetype_fallback
        assert proc.platform == "VTEX"
        assert proc.matches(proc.example_url)
        assert proc.notes and proc.home_url == f"https://{proc.host}/"


def test_etiqueta_solo_talla():
    items = [_item("1", Talla="S"), _item("2", Talla="M")]
    assert tienda.item_labels(items) == {"1": "Talla S", "2": "Talla M"}


def test_etiqueta_omite_el_color_si_no_cambia():
    # Nike: cada color es su ficha; el color termina en punto y el nombre del atributo va en
    # minúsculas (`talle`).
    items = [
        _item("1", talle="H 7 / M 8.5", color="Negro."),
        _item("2", talle="H 8 / M 9.5", color="Negro."),
    ]
    assert tienda.item_labels(items) == {"1": "Talla H 7 / M 8.5", "2": "Talla H 8 / M 9.5"}


def test_etiqueta_con_color_que_cambia_va_primero_y_sin_mayusculas():
    items = [
        _item("1", Talla="S", Color="NEGRO"),
        _item("2", Talla="S", Color="CAFÉ"),
        _item("3", Talla="M", Color="Rojo"),
    ]
    assert tienda.item_labels(items) == {
        "1": "Negro, Talla S",
        "2": "Café, Talla S",
        "3": "Rojo, Talla M",
    }


def test_etiqueta_jeans_y_talla_unica_y_espacios_duros():
    items = [_item("1", Cintura="34", Largo="30"), _item("2", Cintura="36", Largo="30")]
    assert tienda.item_labels(items) == {"1": "Cintura 34, Largo 30", "2": "Cintura 36, Largo 30"}
    assert tienda.item_labels([_item("1", Talla="TALLA ÚNICA")]) == {"1": "Talla única"}
    assert tienda.item_labels([_item("1", Talla="H\xa07 /  M 8.5")]) == {"1": "Talla H 7 / M 8.5"}
    # Solo color: se muestra aunque no cambie.
    assert tienda.item_labels([_item("1", Color="Azul")]) == {"1": "Azul"}
    # Sin atributos: la base agrega el SKU.
    product = {"items": [{"itemId": "7", "variations": []}]}
    assert tienda._labels(product) == {"7": "SKU 7"}


def test_sin_precio_antes_si_la_tienda_lo_desactiva():
    class SinAntes(Tienda):
        supports_list_price = False

    raw = fixture_text("reebok", "mochila_talla_unica.json")
    url = "https://www.tienda.cl/mochila-training-rbk-restore-backpack-mujer-accb123/p"
    con = tienda.parse(raw, tienda.normalize(url))
    sin = SinAntes().parse(raw, SinAntes().normalize(url))
    assert (con.price, con.list_price) == (15996, 39990)
    assert (sin.price, sin.list_price) == (15996, None)
    # Tampoco toma PriceWithoutDiscount como precio "antes".
    data = json.loads(raw)
    offer = data[0]["items"][0]["sellers"][0]["commertialOffer"]
    offer["ListPrice"] = offer["Price"]
    assert SinAntes().parse(json.dumps(data), SinAntes().normalize(url)).list_price is None


@pytest.mark.parametrize(
    "path",
    [
        "/jeans_hombre_straight_tiro_alto/p",
        "/pack-3-camisetas-cuello-redondo-logo%C2%A0-09tcr01965/p",
        "/pack-3-camisetas-cuello-redondo-logo\xa0-09tcr01965/p",
        "/jeans-ae-airflex--slim-con-parches-y-fibras-de-tencel%E2%84%A2-01176308252/p",
        "/zapatillas-classics-bb-4000-ii-%E2%80%9896-unisex-100201680/p",
        "/traje-de-ba%C3%B1o-estampado-juma-coral-1560112642/p",
    ],
)
def test_slugs_raros_de_tiendas_de_ropa(path):
    assert tienda.matches(f"https://www.tienda.cl{path}")


@pytest.mark.parametrize(
    "path", ["/../p", "/a.b/p", "/a%2Fb/p", "/a b/p", "/hombre/polera/p", "/p", "//p"]
)
def test_rutas_que_no_son_fichas(path):
    assert not tienda.matches(f"https://www.tienda.cl{path}")


def _fake_get_text(monkeypatch, responses):
    calls = []

    async def fake(url, **kwargs):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(vtex, "get_text", fake)
    return calls


API = "https://tiendacl.vtexcommercestable.com.br/api/catalog_system/pub"


async def test_agotado_entero_se_busca_por_id(monkeypatch):
    # Levi's: con todas las tallas agotadas la búsqueda por slug da [], pero pagetype
    # resuelve el id y `fq=productId` sí lista el producto.
    agotado = fixture_text("levis", "jeans_505_agotado.json")
    pagetype = json.dumps({"id": "20", "name": "Jeans", "pageType": "Product"})
    calls = _fake_get_text(monkeypatch, ["[]", pagetype, agotado])
    ref = tienda.normalize("https://www.tienda.cl/jeans-hombre-levis-505-regular-00505-1469/p")
    raw = await tienda.fetch_raw(ref)
    assert calls == [
        f"{API}/products/search/jeans-hombre-levis-505-regular-00505-1469/p",
        f"{API}/portal/pagetype/jeans-hombre-levis-505-regular-00505-1469/p",
        f"{API}/products/search?fq=productId:20",
    ]
    r = tienda.parse(raw, ref)
    assert (r.price, r.available) == (59990, False)


@pytest.mark.parametrize(
    "pagetype",
    [
        {"id": None, "name": None, "pageType": "NotFound"},
        {"id": "12", "name": "Zapatillas", "pageType": "Department"},
        {"id": "x1", "pageType": "Product"},
    ],
)
async def test_sin_producto_en_pagetype_no_existe(monkeypatch, pagetype):
    calls = _fake_get_text(monkeypatch, ["[]", json.dumps(pagetype)])
    ref = tienda.normalize("https://www.tienda.cl/no-existe/p")
    with pytest.raises(NotFoundError):
        tienda.parse(await tienda.fetch_raw(ref), ref)
    assert len(calls) == 2


async def test_id_sin_producto_buscable_no_existe(monkeypatch):
    # Nike/Keds: un producto dado de baja sigue en pagetype, pero `fq=productId` da [].
    pagetype = json.dumps({"id": "21256", "pageType": "Product"})
    _fake_get_text(monkeypatch, ["[]", pagetype, "[]"])
    ref = tienda.normalize("https://www.tienda.cl/iu7766-123-nike-dunk-low/p")
    with pytest.raises(NotFoundError):
        tienda.parse(await tienda.fetch_raw(ref), ref)


async def test_slug_que_existe_no_usa_el_respaldo(monkeypatch):
    calls = _fake_get_text(monkeypatch, ["[{}]"])
    assert await tienda.fetch_raw(tienda.normalize("https://www.tienda.cl/polera/p")) == "[{}]"
    assert len(calls) == 1


async def test_otras_tiendas_vtex_no_usan_pagetype(monkeypatch):
    calls = _fake_get_text(monkeypatch, ["[]"])
    jumbo = JumboProcessor()
    ref = jumbo.normalize("https://www.jumbo.cl/no-existe/p")
    with pytest.raises(NotFoundError):
        jumbo.parse(await jumbo.fetch_raw(ref), ref)
    assert len(calls) == 1
