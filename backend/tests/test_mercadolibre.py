"""MercadoLibre: parseo contra respuestas reales de la API y resolución /up/ → catálogo."""

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import fixture_text
from tracker import meli
from tracker.checker import apply_result
from tracker.db import SessionLocal, utcnow
from tracker.models import (
    AlertRule,
    Anomaly,
    Notification,
    OAuthToken,
    PricePoint,
    Product,
    User,
    Watch,
)
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import mercadolibre as mlmod
from tracker.processors.mercadolibre import MercadoLibreProcessor
from tracker.rules import Reading, check_anomaly

ml = MercadoLibreProcessor()
UP_URL = (
    "https://www.mercadolibre.cl/frosthaven-base--juego-de-mesa--en-espanol--diverti/up/"
    "MLCU4406413086#polycard_client=search-desktop&wid=MLC2079328157"
)


def parse(fixture, url):
    return ml.parse(fixture_text("mercadolibre", fixture), ml.normalize(url))


# --- Parseo -------------------------------------------------------------------------------
def test_publicacion_up_sigue_esa_publicacion():
    r = parse("up_frosthaven.json", UP_URL)
    assert r.title == "Juego De Mesa Frosthaven Base Asmodee"
    assert (r.price, r.list_price, r.currency, r.available) == (249990, None, "CLP", True)
    assert r.image_url


def test_catalogo_sigue_la_tienda_oficial_por_defecto():
    # Frosthaven: la tienda oficial (249.990) aunque un nacional lo venda a 248.803.
    r = parse("catalogo_frosthaven.json", "https://www.mercadolibre.cl/p/MLC48419682")
    assert (r.price, r.available) == (249990, True)
    r = parse("catalogo_frosthaven.json", "https://www.mercadolibre.cl/p/MLC48419682?modo=nacional")
    assert (r.price, r.list_price) == (248803, 249990)


SWITCH2 = "https://www.mercadolibre.cl/p/MLC49200061"


def test_catalogo_con_compras_internacionales():
    # Caso real (2026-09-29): 6 ofertas internacionales más baratas, sin garantía; la
    # página muestra la de la tienda oficial de Nintendo.
    r = parse("catalogo_switch2.json", SWITCH2)
    assert (r.price, r.list_price, r.available) == (639262, 659990, True)
    assert parse("catalogo_switch2.json", SWITCH2 + "?modo=nacional").price == 579990
    assert parse("catalogo_switch2.json", SWITCH2 + "?modo=todos").price == 526077


def test_selector_de_ofertas_del_catalogo():
    ref = ml.normalize(SWITCH2)
    variants = ml.parse_variants(fixture_text("mercadolibre", "catalogo_switch2.json"), ref)
    assert [(v.variant_id, v.selected) for v in variants] == [
        ("", True),
        ("nacional", False),
        ("todos", False),
    ]
    assert variants[0].label.startswith("Tienda oficial (o el más barato nacional): $639.262")
    assert "tienda oficial" in variants[0].label
    assert "compra internacional, sin garantía" in variants[2].label
    assert variants[2].url == SWITCH2 + "?modo=todos"
    # Cada URL vuelve a su modo.
    assert [ml.normalize(v.url).variant_id for v in variants] == ["", "nacional", "todos"]


def test_selector_no_repite_la_misma_oferta():
    # Frosthaven no tiene internacionales: "todos" es la misma oferta que "nacional".
    ref = ml.normalize("https://www.mercadolibre.cl/p/MLC48419682")
    variants = ml.parse_variants(fixture_text("mercadolibre", "catalogo_frosthaven.json"), ref)
    assert [v.variant_id for v in variants] == ["", "nacional"]
    # Si el link pide `todos`, se muestra aunque coincida con otra.
    ref = ml.normalize("https://www.mercadolibre.cl/p/MLC48419682?modo=todos")
    variants = ml.parse_variants(fixture_text("mercadolibre", "catalogo_frosthaven.json"), ref)
    assert [v.variant_id for v in variants] == ["", "nacional", "todos"]


def test_publicacion_up_no_tiene_selector():
    ref = ml.normalize(UP_URL)
    assert ml.parse_variants(fixture_text("mercadolibre", "up_frosthaven.json"), ref) == []
    assert ml.variant_label(ref.external_id, ref.variant_id) == ""
    assert ml.variant_label("MLC49200061", "todos").startswith("Más barato, incluidas")


def test_catalogo_con_descuento():
    r = parse("catalogo_con_descuento.json", "https://www.mercadolibre.cl/p/MLC29575879")
    assert (r.price, r.list_price) == (9592, 11990)


def test_catalogo_sin_ofertas_esta_agotado():
    r = parse("catalogo_sin_ofertas.json", "https://www.mercadolibre.cl/p/MLC51856173")
    assert r.title == "Frosthaven - Adhesivos removibles (accesorio)"
    assert (r.price, r.available) == (None, False)


def test_publicacion_que_ya_no_esta_en_el_catalogo_esta_agotada():
    raw = json.loads(fixture_text("mercadolibre", "up_frosthaven.json"))
    raw["items"] = [i for i in raw["items"] if i["user_product_id"] != "MLCU4406413086"]
    r = ml.parse(json.dumps(raw), ml.normalize(UP_URL))
    assert (r.price, r.available) == (None, False)


# --- URLs -----------------------------------------------------------------------------------
def test_normaliza_links():
    up = ml.normalize(UP_URL)
    assert up.external_id == "MLCU4406413086"
    assert up.canonical_url == (
        "https://www.mercadolibre.cl/frosthaven-base--juego-de-mesa--en-espanol--diverti/up/MLCU4406413086"
    )
    cat = ml.normalize(
        "https://mercadolibre.cl/juego-frosthaven/p/mlc48419682?pdp_filters=x#reviews"
    )
    assert (cat.external_id, cat.canonical_url, cat.variant_id) == (
        "MLC48419682",
        "https://www.mercadolibre.cl/p/MLC48419682",
        "",
    )
    nac = ml.normalize("https://www.mercadolibre.cl/p/MLC48419682?modo=nacional&x=1")
    assert (nac.variant_id, nac.canonical_url) == (
        "nacional",
        "https://www.mercadolibre.cl/p/MLC48419682?modo=nacional",
    )
    # Un modo desconocido cae en el por defecto.
    assert ml.normalize("https://www.mercadolibre.cl/p/MLC48419682?modo=raro").variant_id == ""


def test_matchea_solo_productos_de_mercadolibre_chile():
    assert find_processor(UP_URL).name == "mercadolibre"
    assert ml.matches("https://www.mercadolibre.cl/p/MLC48419682")
    assert not ml.matches("https://www.mercadolibre.cl/juegos-de-mesa")
    assert not ml.matches("https://www.mercadolibre.com.ar/p/MLA123")
    assert not ml.matches("https://mercadolibre.cl.evil.com/p/MLC48419682")


# --- Resolución /up/ → catálogo (API simulada) --------------------------------------------
@pytest.fixture
def api(monkeypatch):
    """API simulada: rutas → (status, body). Registra cada path pedido."""
    with SessionLocal() as db:
        db.merge(
            OAuthToken(
                provider=meli.PROVIDER,
                access_token="APP_USR-test",
                refresh_token="TG-test",
                expires_at=utcnow() + timedelta(hours=5),
            )
        )
        db.commit()
    routes, calls = {}, []
    fx = json.loads(fixture_text("mercadolibre", "up_frosthaven.json"))

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        status, body = routes.get(request.url.path, (404, {"message": "No winners found"}))
        return httpx.Response(status, json=body)

    routes["/products/search"] = (200, {"results": [{"id": "MLC99"}, {"id": "MLC48419682"}]})
    routes["/products/MLC99/items"] = (200, {"results": [{"user_product_id": "MLCU1", "price": 5}]})
    routes["/products/MLC48419682/items"] = (200, {"results": fx["items"]})
    routes["/products/MLC48419682"] = (200, fx["product"])
    monkeypatch.setattr(meli, "_transport", httpx.MockTransport(handler))
    mlmod._catalog_of.clear()
    return routes, calls


async def test_resuelve_el_catalogo_de_una_publicacion_una_sola_vez(api):
    _, calls = api
    r = await ml.fetch(ml.normalize(UP_URL))
    assert (r.price, r.available) == (249990, True)
    assert "/products/search" in calls and mlmod._catalog_of["MLCU4406413086"] == "MLC48419682"
    calls.clear()
    await ml.fetch(ml.normalize(UP_URL))
    assert "/products/search" not in calls  # quedó en memoria


async def test_publicacion_sin_catalogo_da_error_claro(api):
    routes, _ = api
    routes["/products/search"] = (200, {"results": [{"id": "MLC99"}]})
    with pytest.raises(NotFoundError, match="link del catálogo"):
        await ml.fetch(ml.normalize(UP_URL))


async def test_sin_cuenta_conectada_es_fetch_error(api):
    with SessionLocal() as db:
        db.delete(db.get(OAuthToken, meli.PROVIDER))
        db.commit()
    with pytest.raises(FetchError, match="no está conectado"):
        await ml.fetch(ml.normalize("https://www.mercadolibre.cl/p/MLC48419682"))


# --- Agotado sin precio: no es anomalía en MercadoLibre -----------------------------------
def test_sin_precio_ni_stock_solo_es_normal_si_el_procesador_lo_declara():
    agotado = Reading(None, None, False)
    assert check_anomaly(agotado, 1000)[0] == "price_none"
    assert check_anomaly(agotado, 1000, sold_out_without_price=True) is None
    # Sin precio pero "disponible" sigue siendo un parseo roto.
    assert check_anomaly(Reading(None, None, True), 1000, sold_out_without_price=True)


async def test_agotado_y_vuelta_a_stock_en_mercadolibre(session):
    user = User(username="ana", role="user", active=True)
    product = Product(
        processor="mercadolibre",
        external_id="MLC48419682",
        canonical_url="https://www.mercadolibre.cl/p/MLC48419682",
        title="Frosthaven",
        currency="CLP",
    )
    session.add_all([user, product])
    session.flush()
    session.add(
        PricePoint(product_id=product.id, price=248803, available=True, checked_at=utcnow())
    )
    watch = Watch(user_id=user.id, product_id=product.id, active=True, price_at_start=248803)
    session.add(watch)
    session.flush()
    for kind in ("OUT_OF_STOCK", "BACK_IN_STOCK"):
        session.add(
            AlertRule(watch_id=watch.id, kind=kind, params={}, state={"last_available": True})
        )
    session.commit()

    agotado = ml.parse(
        fixture_text("mercadolibre", "catalogo_sin_ofertas.json"),
        ml.normalize(product.canonical_url),
    )
    out = await apply_result(session, product, agotado)
    assert out.ok and out.anomaly is None
    assert session.scalars(select(Anomaly)).all() == []
    en_stock = ml.parse(
        fixture_text("mercadolibre", "catalogo_frosthaven.json"),
        ml.normalize(product.canonical_url),
    )
    await apply_result(session, product, en_stock)
    kinds = [
        f["kind"] for n in session.scalars(select(Notification)).all() for f in n.payload["fired"]
    ]
    assert kinds == ["OUT_OF_STOCK", "BACK_IN_STOCK"]
