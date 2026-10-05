"""Tests puros del RuleEngine (sin DB)."""

import pytest

from tracker.rules import (
    Reading,
    RuleError,
    check_anomaly,
    evaluate,
    initial_state,
    validate_params,
)


def run(kind, params, prices, *, start=None, available=True, list_price=None, state=None):
    """Aplica una secuencia de precios; devuelve en qué lecturas se disparó."""
    state = state if state is not None else initial_state(kind, None)
    hits = []
    for i, p in enumerate(prices):
        fired, state = evaluate(
            kind, params, state, Reading(p, list_price, available), price_at_start=start
        )
        if fired:
            hits.append(i)
    return hits, state


# --- TARGET_PRICE --------------------------------------------------------------------
def test_objetivo_dispara_una_vez_y_no_repite_por_oscilacion():
    hits, _ = run("TARGET_PRICE", {"value": 10000}, [12000, 9990, 9500, 10100, 9900])
    # 10100 no supera 10000 + 2 %: sigue desarmada, así que 9900 no vuelve a avisar.
    assert hits == [1]


def test_objetivo_se_rearma_al_volver_del_otro_lado():
    hits, _ = run("TARGET_PRICE", {"value": 10000}, [9000, 11000, 9500])
    assert hits == [0, 2]


def test_objetivo_no_avisa_sin_stock():
    hits, state = run("TARGET_PRICE", {"value": 10000}, [9000], available=False)
    assert hits == []
    assert state["armed"] is True


# --- DISCOUNT_PCT --------------------------------------------------------------------
def test_descuento_base_watch_start():
    params = {"pct": 20, "baseline": "watch_start"}
    hits, _ = run("DISCOUNT_PCT", params, [10000, 8500, 7900, 7800], start=10000)
    assert hits == [2]


def test_descuento_base_list_price():
    params = {"pct": 30, "baseline": "list_price"}
    hits, _ = run("DISCOUNT_PCT", params, [7000], list_price=10000)
    assert hits == [0]
    hits, _ = run("DISCOUNT_PCT", params, [7500], list_price=10000)
    assert hits == []


def test_descuento_base_list_price_sin_dato_no_dispara():
    hits, _ = run("DISCOUNT_PCT", {"pct": 10, "baseline": "list_price"}, [1], list_price=None)
    assert hits == []


def test_descuento_base_fija():
    params = {"pct": 50, "baseline": {"fixed": 20000}}
    hits, _ = run("DISCOUNT_PCT", params, [15000, 10000, 9000], start=99999)
    assert hits == [1]


def test_descuento_histeresis():
    params = {"pct": 20, "baseline": {"fixed": 10000}}
    # 20 % → dispara; 19 % no re-arma (umbral - 2 puntos = 18); 17 % re-arma; 20 % vuelve a avisar.
    hits, _ = run("DISCOUNT_PCT", params, [8000, 8100, 8000, 8300, 8000])
    assert hits == [0, 4]


# --- PRICE_DROP / PRICE_UP ----------------------------------------------------------
def test_bajada_compara_contra_ultimo_notificado():
    # Bajadas de 3 % acumuladas: avisa al llegar a 10 % respecto del último notificado.
    hits, state = run("PRICE_DROP", {"min_pct": 10}, [10000, 9700, 9400, 9000, 8800, 8100])
    assert hits == [3, 5]
    assert state["last_notified_price"] == 8100


def test_bajada_primera_lectura_es_referencia():
    hits, state = run("PRICE_DROP", {"min_pct": 5}, [10000])
    assert hits == []
    assert state["last_notified_price"] == 10000


def test_bajada_con_estado_inicial_del_watch():
    state = initial_state("PRICE_DROP", Reading(10000, None, True))
    hits, _ = run("PRICE_DROP", {"min_pct": 5}, [9400], state=state)
    assert hits == [0]


def test_subida():
    # 11000 es +10 % sobre 10000; 12200 es +10,9 % sobre el último notificado (11000).
    hits, _ = run("PRICE_UP", {"min_pct": 10}, [10000, 10500, 11000, 11500, 12000, 12200])
    assert hits == [2, 5]


def test_oscilacion_no_genera_ruido():
    hits, _ = run("PRICE_DROP", {"min_pct": 10}, [10000, 9500, 10000, 9500, 10000])
    assert hits == []


# --- Stock ---------------------------------------------------------------------------
def test_sin_stock_y_vuelta():
    state_out = initial_state("OUT_OF_STOCK", Reading(100, None, True))
    state_back = initial_state("BACK_IN_STOCK", Reading(100, None, True))
    seq = [True, False, False, True]
    out_hits, back_hits = [], []
    for i, avail in enumerate(seq):
        f, state_out = evaluate("OUT_OF_STOCK", {}, state_out, Reading(100, None, avail))
        if f:
            out_hits.append(i)
        f, state_back = evaluate("BACK_IN_STOCK", {}, state_back, Reading(100, None, avail))
        if f:
            back_hits.append(i)
    assert out_hits == [1]
    assert back_hits == [3]


def test_stock_sin_estado_previo_no_dispara():
    fired, state = evaluate("BACK_IN_STOCK", {}, {"last_available": None}, Reading(1, None, True))
    assert fired is None
    assert state["last_available"] is True


# --- Varias reglas en la misma lectura --------------------------------------------------
def test_varias_reglas_disparan_en_la_misma_lectura():
    reading = Reading(7000, 10000, True)
    specs = [
        ("TARGET_PRICE", {"value": 8000}, {"armed": True}),
        ("DISCOUNT_PCT", {"pct": 25, "baseline": "list_price"}, {"armed": True}),
        ("PRICE_DROP", {"min_pct": 10}, {"last_notified_price": 9000}),
        ("PRICE_UP", {"min_pct": 10}, {"last_notified_price": 9000}),
    ]
    fired = [evaluate(k, p, s, reading, price_at_start=9000)[0] for k, p, s in specs]
    assert [f.kind if f else None for f in fired] == [
        "TARGET_PRICE",
        "DISCOUNT_PCT",
        "PRICE_DROP",
        None,
    ]


def test_evaluate_no_muta_el_estado():
    state = {"armed": True}
    evaluate("TARGET_PRICE", {"value": 10}, state, Reading(5, None, True))
    assert state == {"armed": True}


# --- Anomalías ------------------------------------------------------------------------
def test_anomalia_precio_none():
    assert check_anomaly(Reading(None, None, True), 1000)[0] == "price_none"


def test_anomalia_caida_mayor_a_80():
    assert check_anomaly(Reading(1500, None, True), 10000)[0] == "big_drop"
    assert check_anomaly(Reading(2100, None, True), 10000) is None


# --- PRICE_CHANGE --------------------------------------------------------------------
def test_varia_avisa_cada_cambio_respecto_de_la_lectura_anterior():
    # Sin anti-spam: cada cambio avisa, incluso las oscilaciones; repetir precio no.
    hits, state = run("PRICE_CHANGE", {}, [10000, 10000, 9990, 10000, 10000, 12000])
    assert hits == [2, 3, 5]
    assert state["last_price"] == 12000


def test_varia_mensaje_con_signo_y_referencia():
    fired, _ = evaluate("PRICE_CHANGE", {}, {"last_price": 10000}, Reading(9000, None, True))
    assert fired.message == "El precio varió -10 %" and fired.data == {"from": 10000}
    fired, _ = evaluate("PRICE_CHANGE", {}, {"last_price": 10000}, Reading(10050, None, True))
    assert fired.message == "El precio varió +0,5 %"


def test_varia_desde_gratis_y_sin_stock():
    fired, _ = evaluate("PRICE_CHANGE", {}, {"last_price": 0}, Reading(5000, None, True))
    assert fired is not None
    # Sin stock no se evalúa ni se mueve la referencia.
    fired, state = evaluate("PRICE_CHANGE", {}, {"last_price": 100}, Reading(90, None, False))
    assert fired is None and state["last_price"] == 100


def test_varia_no_tiene_parametros():
    assert validate_params("PRICE_CHANGE", {"x": 1}) == {}
    assert initial_state("PRICE_CHANGE", Reading(7000, None, True)) == {"last_price": 7000}


def test_umbral_de_caida_configurable():
    assert check_anomaly(Reading(500, None, True), 10000, max_drop_pct=None) is None
    assert check_anomaly(Reading(500, None, True), 10000, max_drop_pct=90)[0] == "big_drop"
    assert check_anomaly(Reading(None, None, True), 10000, max_drop_pct=None)[0] == "price_none"


def test_primera_lectura_no_es_anomalia():
    assert check_anomaly(Reading(10, None, True), None) is None


# --- Validación ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kind", "params"),
    [
        ("TARGET_PRICE", {"value": 1.5}),
        ("TARGET_PRICE", {}),
        ("DISCOUNT_PCT", {"pct": 150}),
        ("DISCOUNT_PCT", {"pct": 10, "baseline": "otra"}),
        ("DISCOUNT_PCT", {"pct": 10, "baseline": {"fixed": -1}}),
        ("PRICE_DROP", {"min_pct": 0}),
        ("NO_EXISTE", {}),
    ],
)
def test_parametros_invalidos(kind, params):
    with pytest.raises(RuleError):
        validate_params(kind, params)


def test_parametros_validos():
    assert validate_params("DISCOUNT_PCT", {"pct": 10}) == {"pct": 10, "baseline": "watch_start"}
    assert validate_params("DISCOUNT_PCT", {"pct": 10, "baseline": {"fixed": 5000}})[
        "baseline"
    ] == {"fixed": 5000}
