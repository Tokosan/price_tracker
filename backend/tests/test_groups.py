"""Watches con varios links: lectura del grupo, avisos y la API para armarlos."""

from datetime import timedelta

from sqlalchemy import select, update

from tests.test_api import BILLY, STARDEW, logged_in, sin_red  # noqa: F401 (fixture autouse)
from tracker import groups, rules
from tracker.checker import apply_result
from tracker.db import SessionLocal, utcnow
from tracker.models import AlertRule, Notification, PricePoint, Product, User, Watch, WatchItem
from tracker.processors import ScrapeResult

BILLY2 = "https://www.ikea.com/cl/es/p/billy-estante-blanco-50508652/"


# --- Lectura del grupo y avisos ---------------------------------------------------------------
def setup_group(session, specs, prices, processors=("steam", "ikea")):
    """Un Watch con un item por procesador; cada item con una lectura de hace 1 h."""
    user = User(username="ana", role="user", active=True)
    session.add(user)
    products = []
    for i, (proc, price) in enumerate(zip(processors, prices, strict=True)):
        p = Product(
            processor=proc,
            external_id=str(i),
            canonical_url=f"https://{proc}.example/{i}",
            title=f"Item {proc}",
            currency="CLP",
        )
        session.add(p)
        session.flush()
        session.add(
            PricePoint(
                product_id=p.id,
                price=price,
                available=price is not None,
                checked_at=utcnow() - timedelta(hours=1),
            )
        )
        products.append(p)
    best = min(p for p in prices if p is not None)
    watch = Watch(
        user_id=user.id,
        name="Estante",
        price_at_start=best,
        last_price=best,
        last_available=True,
        counted_product_ids=sorted(p.id for p in products),
        items=[WatchItem(product_id=p.id, user_id=user.id) for p in products],
    )
    session.add(watch)
    session.flush()
    for kind, params, state in specs:
        session.add(AlertRule(watch_id=watch.id, kind=kind, params=params, state=state))
    session.commit()
    return products, watch


def scrape(price, available=True, title="Item"):
    return ScrapeResult(title, price, None, "CLP", available, None)


async def test_el_grupo_avisa_una_vez_por_el_mas_barato_con_su_tienda(session):
    (_, ikea), watch = setup_group(
        session, [("PRICE_DROP", {"min_pct": 5}, {"last_notified_price": 10000})], [10000, 12000]
    )
    # Baja el que no era el más barato, pero queda bajo el anterior: el ganador cambia.
    await apply_result(session, ikea, scrape(9000, title="Item ikea"))
    notif = session.scalars(select(Notification)).one()
    assert notif.payload["title"] == "Estante"
    assert notif.payload["price"] == 9000
    assert notif.payload["product_id"] == ikea.id
    assert notif.payload["processor"] == "ikea"
    assert notif.payload["url"] == ikea.canonical_url
    watch = session.get(Watch, watch.id)
    assert (watch.last_price, watch.last_best_product_id) == (9000, ikea.id)


async def test_un_item_caro_que_cambia_no_mueve_el_grupo(session):
    (_, ikea), _ = setup_group(
        session, [("PRICE_CHANGE", {}, {"last_price": 10000})], [10000, 12000]
    )
    await apply_result(session, ikea, scrape(11000))
    assert session.scalars(select(Notification)).all() == []


async def test_agotado_cuando_se_agotan_todos(session):
    (steam, ikea), _ = setup_group(
        session,
        [("OUT_OF_STOCK", {}, {"last_available": True})],
        [10000, 12000],
    )
    await apply_result(session, steam, scrape(10000, available=False))
    assert session.scalars(select(Notification)).all() == []  # queda IKEA con stock
    await apply_result(session, ikea, scrape(12000, available=False))
    fired = session.scalars(select(Notification)).one().payload["fired"]
    assert [f["kind"] for f in fired] == ["OUT_OF_STOCK"]


def test_items_viejos_o_broken_no_cuentan(session):
    (steam, ikea), watch = setup_group(session, [], [10000, 12000])
    now = utcnow()
    assert groups.best_item(groups.item_states(session, watch, now)).product.id == steam.id
    steam.status = "broken"
    assert groups.best_item(groups.item_states(session, watch, now)).product.id == ikea.id
    steam.status = "ok"
    # Las dos tiendas se revisan cada 6 h: con más de 18 h sin lectura, deja de contar.
    session.scalar(select(PricePoint).where(PricePoint.product_id == ikea.id)).checked_at = now
    states = groups.item_states(session, watch, now + timedelta(hours=17, minutes=30))
    assert [s.counts for s in states] == [False, True]
    assert groups.best_item(states).product.id == ikea.id


def test_sin_stock_en_ninguno_la_lectura_es_sin_stock(session):
    products, watch = setup_group(session, [], [10000, 12000])
    for p in session.scalars(select(PricePoint)):
        p.available = False
    reading, best = groups.group_reading(session, watch, utcnow())
    assert reading == rules.Reading(10000, None, False)
    assert best.product.id == products[0].id


async def test_mensaje_de_grupo_dice_donde_esta_el_precio(session):
    from tracker.checker import build_message

    (_, ikea), _ = setup_group(session, [], [10000, 12000])
    fired = [rules.Fired("PRICE_CHANGE", "El precio varió -10 %", {"from": 10000})]
    text = build_message(
        "Estante",
        ikea,
        rules.Reading(9000, None, True),
        fired,
        False,
        10000,
        store="IKEA",
        previous_store="Steam",
    )
    assert text.split("\n")[:2] == ["<b>Estante</b>", "$9.000 en IKEA (antes $10.000 en Steam)"]


async def test_un_item_broken_no_dispara_alertas(session):
    (steam, ikea), _ = setup_group(
        session, [("PRICE_UP", {"min_pct": 5}, {"last_notified_price": 10000})], [10000, 12000]
    )
    steam.status = "broken"
    session.commit()
    # El más barato quedó fuera: el grupo "sube" a 12.000, pero eso no es un cambio de precio.
    await apply_result(session, ikea, scrape(12000))
    assert session.scalars(select(Notification)).all() == []
    # Steam se recupera con su precio de siempre: tampoco es una bajada.
    await apply_result(session, steam, scrape(10000))
    assert session.scalars(select(Notification)).all() == []


async def test_un_item_que_deja_de_leerse_no_dispara_alertas(session):
    (steam, ikea), _ = setup_group(
        session,
        [
            ("PRICE_CHANGE", {}, {"last_price": 10000}),
            ("OUT_OF_STOCK", {}, {"last_available": True}),
        ],
        [10000, 12000],
    )
    session.execute(
        update(PricePoint)
        .where(PricePoint.product_id == steam.id)
        .values(checked_at=utcnow() - timedelta(hours=30))
    )
    session.commit()
    await apply_result(session, ikea, scrape(12000, available=False))
    assert session.scalars(select(Notification)).all() == []
    # Desde ahí, un cambio real sí avisa.
    await apply_result(session, ikea, scrape(11000))
    fired = session.scalars(select(Notification)).one().payload["fired"]
    assert [f["kind"] for f in fired] == ["PRICE_CHANGE"]


async def test_cambiar_los_links_no_repite_un_objetivo_ya_avisado(session):
    from tracker.api.watches import reset_group

    (steam, _), watch = setup_group(
        session, [("TARGET_PRICE", {"value": 11000}, {"armed": False})], [10000, 12000]
    )
    reset_group(session, session.get(Watch, watch.id))
    session.commit()
    await apply_result(session, steam, scrape(10000))
    assert session.scalars(select(Notification)).all() == []


# --- API -----------------------------------------------------------------------------------------
def test_crear_un_producto_con_varios_links_y_nombre():
    api = logged_in("ana")
    r = api.post(
        "/api/watches",
        {"urls": [STARDEW, BILLY], "rules": [], "mode": "group", "name": "  Cosas  "},
    )
    assert r.status_code == 201, r.text
    (w,) = r.json()
    assert w["name"] == "Cosas" and w["display_name"] == "Cosas"
    assert [i["processor"] for i in w["items"]] == ["steam", "ikea"]
    assert w["best"]["processor"] == "steam" and w["best"]["price"] == 7500
    assert w["price_at_start"] == 7500
    assert [i["best"] for i in w["items"]] == [True, False]
    hist = api.get(f"/api/watches/{w['id']}/history").json()["items"]
    assert [h["processor"] for h in hist] == ["steam", "ikea"]
    assert all(len(h["points"]) == 1 for h in hist)


def test_un_link_va_en_un_solo_producto():
    api = logged_in("ana")
    api.post("/api/watches", {"urls": [STARDEW], "rules": []})
    r = api.post("/api/watches", {"urls": [BILLY, STARDEW], "rules": [], "mode": "group"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_watching"
    # En modo separado se devuelve el que ya existe, como siempre.
    r = api.post("/api/watches", {"urls": [STARDEW], "rules": []})
    assert r.status_code == 201 and len(api.get("/api/watches").json()) == 1
    resolved = api.post("/api/resolve", {"url": STARDEW}).json()
    assert resolved["watching_in"]["name"] == "Stardew Valley"


def test_monedas_distintas_no_se_juntan():
    api = logged_in("ana")
    w = api.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    api.post("/api/resolve", {"url": BILLY})
    with SessionLocal() as db:
        db.scalar(select(Product).where(Product.processor == "ikea")).currency = "USD"
        db.commit()
    r = api.post(f"/api/watches/{w['id']}/items", {"url": BILLY})
    assert r.status_code == 422 and "moneda" in r.json()["detail"]


def test_renombrar_y_volver_al_titulo_de_la_tienda():
    api = logged_in("ana")
    w = api.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    r = api.patch(f"/api/watches/{w['id']}", {"name": "Granjita"})
    assert r.json()["display_name"] == "Granjita"
    # Un PATCH sin `name` no lo toca.
    assert api.patch(f"/api/watches/{w['id']}", {"active": True}).json()["name"] == "Granjita"
    r = api.patch(f"/api/watches/{w['id']}", {"name": "  "})
    assert r.json()["name"] is None and r.json()["display_name"] == "Stardew Valley"


def test_agregar_y_quitar_links():
    api = logged_in("ana")
    w = api.post(
        "/api/watches",
        {"urls": [BILLY], "rules": [{"kind": "PRICE_DROP", "params": {"min_pct": 5}}]},
    ).json()[0]
    r = api.post(f"/api/watches/{w['id']}/items", {"url": STARDEW})
    assert r.status_code == 201, r.text
    w = r.json()
    assert w["best"]["processor"] == "steam"
    with SessionLocal() as db:
        # La lectura del grupo cambió de golpe: la regla parte desde el precio nuevo.
        rule = db.scalar(select(AlertRule))
        assert rule.state == {"last_notified_price": 7500}
    steam_id = next(i["id"] for i in w["items"] if i["processor"] == "steam")
    ikea_id = next(i["id"] for i in w["items"] if i["processor"] == "ikea")
    r = api.delete(f"/api/watches/{w['id']}/items/{steam_id}")
    assert [i["processor"] for i in r.json()["watch"]["items"]] == ["ikea"]
    # Quitar el último link borra el producto.
    assert api.delete(f"/api/watches/{w['id']}/items/{ikea_id}").json() == {"watch": None}
    assert api.get("/api/watches").json() == []


def test_mover_el_ultimo_link_lleva_sus_avisos():
    api = logged_in("ana")
    a = api.post("/api/watches", {"urls": [BILLY], "rules": []}).json()[0]
    b = api.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    with SessionLocal() as db:
        db.add(Notification(watch_id=b["id"], payload={"title": "viejo"}, delivery={}))
        db.commit()
    pid = b["items"][0]["id"]
    r = api.post(f"/api/watches/{b['id']}/items/{pid}/move", {"to": a["id"]})
    assert r.json()["source"] is None
    notifs = api.get(f"/api/notifications?watch_id={a['id']}").json()
    assert [n["payload"]["title"] for n in notifs] == ["viejo"]


def test_mover_un_link_a_un_producto_nuevo_copia_las_reglas():
    api = logged_in("ana")
    w = api.post(
        "/api/watches",
        {
            "urls": [BILLY, BILLY2],
            "rules": [{"kind": "TARGET_PRICE", "params": {"value": 50000}}],
            "mode": "group",
        },
    ).json()[0]
    pid = w["items"][1]["id"]
    r = api.post(f"/api/watches/{w['id']}/items/{pid}/move", {"to": None})
    assert r.status_code == 200, r.text
    assert len(r.json()["source"]["items"]) == 1
    target = r.json()["target"]
    assert [i["id"] for i in target["items"]] == [pid]
    assert [x["kind"] for x in target["rules"]] == ["TARGET_PRICE"]
    # Y de vuelta al original: el que queda vacío se borra.
    r = api.post(f"/api/watches/{target['id']}/items/{pid}/move", {"to": w["id"]})
    assert r.json()["source"] is None
    assert len(r.json()["target"]["items"]) == 2
    assert len(api.get("/api/watches").json()) == 1


def test_juntar_productos():
    api = logged_in("ana")
    a = api.post("/api/watches", {"urls": [BILLY], "rules": [{"kind": "BACK_IN_STOCK"}]}).json()[0]
    b = api.post(
        "/api/watches",
        {"urls": [STARDEW], "rules": [{"kind": "PRICE_DROP", "params": {"min_pct": 5}}]},
    ).json()[0]
    api.patch(f"/api/watches/{a['id']}", {"name": "Principal"})
    with SessionLocal() as db:
        db.add(Notification(watch_id=b["id"], payload={"title": "viejo"}, delivery={}))
        db.commit()
    otro = logged_in("beto")
    assert otro.post("/api/watches/merge", {"ids": [a["id"], b["id"]]}).status_code == 404

    r = api.post("/api/watches/merge", {"ids": [b["id"], a["id"]]})
    assert r.status_code == 200, r.text
    m = r.json()
    # El principal es el más antiguo: conserva nombre y reglas; las del otro se descartan.
    assert m["id"] == a["id"] and m["name"] == "Principal"
    assert [x["kind"] for x in m["rules"]] == ["BACK_IN_STOCK"]
    assert {i["processor"] for i in m["items"]} == {"steam", "ikea"}
    assert m["price_at_start"] == 7500  # el mínimo de los dos
    assert [w["id"] for w in api.get("/api/watches").json()] == [a["id"]]
    notifs = api.get(f"/api/notifications?watch_id={a['id']}").json()
    assert [n["payload"]["title"] for n in notifs] == ["viejo"]
    with SessionLocal() as db:
        assert db.scalars(select(AlertRule)).all()[0].watch_id == a["id"]
        assert len(db.scalars(select(AlertRule)).all()) == 1


def test_maximo_de_links():
    from tracker.api import watches as watches_api

    api = logged_in("ana")
    w = api.post("/api/watches", {"urls": [STARDEW, BILLY], "rules": [], "mode": "group"})
    assert w.status_code == 201
    old, watches_api.MAX_ITEMS = watches_api.MAX_ITEMS, 2
    try:
        r = api.post(f"/api/watches/{w.json()[0]['id']}/items", {"url": BILLY2})
        assert r.status_code == 422
    finally:
        watches_api.MAX_ITEMS = old


def test_revisar_ahora_revisa_todos_los_links():
    api = logged_in("ana")
    w = api.post("/api/watches", {"urls": [STARDEW, BILLY], "rules": [], "mode": "group"}).json()[0]
    r = api.post(f"/api/watches/{w['id']}/check")
    assert r.status_code == 200, r.text
    assert r.json()["outcome"]["checked"] == 2
    assert r.json()["watch"]["manual_check_available_at"] is not None
    assert api.post(f"/api/watches/{w['id']}/check").status_code == 429
