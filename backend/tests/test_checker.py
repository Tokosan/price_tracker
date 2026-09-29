"""Flujo de revisión contra la DB, sin red."""

from datetime import timedelta

from sqlalchemy import select

from tracker import checker, rules
from tracker.checker import (
    apply_result,
    backoff_delay,
    build_message,
    next_check,
    record_failure,
)
from tracker.db import utcnow
from tracker.models import AlertRule, Anomaly, Notification, PricePoint, Product, User, Watch
from tracker.processors import ScrapeResult

URLS = {
    "steam": "https://store.steampowered.com/app/1/",
    "ikea": "https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/",
}


def setup_watch(session, rules_spec, price_at_start=10000, processor="steam"):
    user = User(username="ana", role="user", active=True)
    product = Product(
        processor=processor,
        external_id="1",
        canonical_url=URLS[processor],
        title="Juego",
        currency="CLP",
    )
    session.add_all([user, product])
    session.flush()
    session.add(
        PricePoint(
            product_id=product.id,
            price=price_at_start,
            available=True,
            checked_at=utcnow() - timedelta(days=1),
        )
    )
    watch = Watch(user_id=user.id, product_id=product.id, price_at_start=price_at_start)
    session.add(watch)
    session.flush()
    for kind, params, state in rules_spec:
        session.add(AlertRule(watch_id=watch.id, kind=kind, params=params, state=state))
    session.commit()
    return product, watch


def result(price, available=True, list_price=None):
    return ScrapeResult("Juego", price, list_price, "CLP", available, None)


async def test_una_notificacion_consolidada_por_lectura(session):
    product, watch = setup_watch(
        session,
        [
            ("TARGET_PRICE", {"value": 8000}, {"armed": True}),
            ("PRICE_DROP", {"min_pct": 10}, {"last_notified_price": 10000}),
        ],
    )
    outcome = await apply_result(session, product, result(7500))
    assert outcome.ok
    notifs = session.scalars(select(Notification)).all()
    assert len(notifs) == 1
    kinds = [f["kind"] for f in notifs[0].payload["fired"]]
    assert kinds == ["TARGET_PRICE", "PRICE_DROP"]
    assert notifs[0].payload["historic_min"] is True
    # El estado de las reglas quedó guardado.
    session.expire_all()
    states = {r.kind: r.state for r in session.get(Watch, watch.id).rules}
    assert states["TARGET_PRICE"]["armed"] is False
    assert states["PRICE_DROP"]["last_notified_price"] == 7500


async def test_caida_absurda_es_anomalia_y_no_alerta(session):
    product, _ = setup_watch(
        session, [("TARGET_PRICE", {"value": 8000}, {"armed": True})], processor="ikea"
    )
    outcome = await apply_result(session, product, result(990))
    assert not outcome.ok and outcome.anomaly == "big_drop"
    assert session.scalars(select(Notification)).all() == []
    assert len(session.scalars(select(Anomaly)).all()) == 1
    # No se guardó el PricePoint sospechoso.
    assert session.scalars(select(PricePoint.price)).all() == [10000]


async def test_oferta_de_90_en_steam_no_es_anomalia_y_alerta(session):
    product, _ = setup_watch(session, [("TARGET_PRICE", {"value": 8000}, {"armed": True})])
    outcome = await apply_result(session, product, result(1000))
    assert outcome.ok and outcome.anomaly is None
    assert session.scalars(select(Anomaly)).all() == []
    assert len(session.scalars(select(Notification)).all()) == 1
    assert sorted(session.scalars(select(PricePoint.price)).all()) == [1000, 10000]


async def test_juego_regalado_en_steam_no_es_anomalia(session):
    product, _ = setup_watch(session, [("PRICE_DROP", {"min_pct": 0}, {})])
    outcome = await apply_result(session, product, result(0))
    assert outcome.ok and outcome.anomaly is None


async def test_precio_none_es_anomalia(session):
    product, _ = setup_watch(session, [("OUT_OF_STOCK", {}, {"last_available": True})])
    outcome = await apply_result(session, product, result(None, available=False))
    assert outcome.anomaly == "price_none"
    assert session.scalars(select(Notification)).all() == []


async def test_usuario_inactivo_no_recibe_alertas(session):
    product, watch = setup_watch(session, [("TARGET_PRICE", {"value": 8000}, {"armed": True})])
    session.get(User, watch.user_id).active = False
    session.commit()
    await apply_result(session, product, result(7000))
    assert session.scalars(select(Notification)).all() == []


async def test_fallos_seguidos_dejan_el_producto_broken(session):
    product, _ = setup_watch(session, [])
    for _ in range(checker.BROKEN_AFTER):
        await record_failure(product.id, "HTTP 500")
    session.expire_all()
    p = session.get(Product, product.id)
    assert p.status == "broken"
    assert p.fail_count == checker.BROKEN_AFTER
    # Una lectura buena lo recupera.
    await apply_result(session, p, result(10000))
    assert p.status == "ok" and p.fail_count == 0


def test_backoff_exponencial_con_tope():
    assert [backoff_delay(n).total_seconds() / 3600 for n in (1, 2, 3, 4)] == [1, 2, 4, 8]
    assert backoff_delay(20) == timedelta(hours=24)


def test_jitter_de_20_por_ciento():
    now = utcnow()
    for _ in range(200):
        delta = next_check(timedelta(hours=10), now) - now
        assert timedelta(hours=8) <= delta <= timedelta(hours=12)


async def test_el_antes_del_aviso_es_la_lectura_anterior_no_el_precio_normal(session):
    # Caso real de MercadoLibre: precio normal 249.990, la lectura anterior 248.803.
    product, _ = setup_watch(session, [("PRICE_CHANGE", {}, {"last_price": 248803})], 248803)
    await apply_result(session, product, result(249966, list_price=249990))
    payload = session.scalars(select(Notification)).one().payload
    assert payload["previous_price"] == 248803
    assert payload["list_price"] == 249990


def test_mensaje_muestra_antes_y_precio_normal_por_separado():
    product = Product(title="Frosthaven", canonical_url="https://x/1")
    fired = [rules.Fired("PRICE_CHANGE", "El precio varió +0.5 %", {"from": 248803})]
    text = build_message(product, result(249966, list_price=249990), fired, False, 248803)
    lines = text.split("\n")
    assert lines[1] == "$249.966 (antes $248.803)"
    assert lines[2] == "Precio normal $249.990"
    # El "desde" repetiría el "antes": no se agrega.
    assert lines[3] == "• El precio varió +0.5 %"


def test_mensaje_conserva_el_desde_del_ultimo_aviso():
    product = Product(title="Juego", canonical_url="https://x/1")
    fired = [rules.Fired("PRICE_DROP", "Bajó 20 %", {"from": 10000})]
    text = build_message(product, result(8000), fired, False, 9000)
    assert "$8.000 (antes $9.000)" in text
    assert "• Bajó 20 % (desde $10.000)" in text
