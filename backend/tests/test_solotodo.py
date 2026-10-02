import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import PROCESSORS, FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.solotodo import SolotodoProcessor

st = SolotodoProcessor()

REFURB = "https://schema.org/RefurbishedCondition"
NEW = "https://schema.org/NewCondition"


def ref(product_id: str, mode: str = "") -> ProductRef:
    url = f"https://www.solotodo.cl/products/{product_id}" + (f"?modo={mode}" if mode else "")
    return ProductRef(product_id, url, mode)


def test_esta_registrado():
    assert PROCESSORS["solotodo"].label == "Solotodo"
    assert find_processor("https://www.solotodo.cl/products/265617").name == "solotodo"
    assert st.sold_out_without_price is True
    assert st.supports_list_price is False


def test_varias_tiendas_toma_el_minimo_offer_price():
    # A-DATA Legend 860 2 TB: 11 tiendas, todas nuevas; la más barata, $338.541.
    r = st.parse(fixture_text("solotodo", "varias_tiendas.json"), ref("265617"))
    assert r.title == "A-DATA Legend 860 2 TB (SLEG-860-2000GCS)"
    assert r.price == 338541  # offer_price "338541.00", no normal_price (358.111)
    assert r.list_price is None
    assert r.currency == "CLP"
    assert r.available is True
    assert r.image_url == "https://media.solotodo.com/media/products/2016851_picture_1739199052.png"


def test_varias_tiendas_sin_reacondicionados_ofrece_un_solo_modo():
    raw = fixture_text("solotodo", "varias_tiendas.json")
    variants = st.parse_variants(raw, ref("265617"))
    assert [(v.variant_id, v.label, v.selected) for v in variants] == [
        ("", "Solo nuevos: $338.541 (11 tiendas)", True)
    ]
    # Pero si el link pide "todos", ese modo aparece igual.
    variants = st.parse_variants(raw, ref("265617", "todos"))
    assert [v.variant_id for v in variants] == ["", "todos"]
    assert variants[1].selected


def test_solo_reacondicionado_queda_agotado_por_defecto():
    # WD Blue 500 GB: la única oferta es reacondicionada (Winpy, $17.632).
    raw = fixture_text("solotodo", "solo_reacondicionado.json")
    r = st.parse(raw, ref("143685"))
    assert r.title == "Western Digital Blue 500 GB (WD5000LPZX)"
    assert r.price is None
    assert r.available is False


def test_solo_reacondicionado_en_modo_todos():
    raw = fixture_text("solotodo", "solo_reacondicionado.json")
    r = st.parse(raw, ref("143685", "todos"))
    assert r.price == 17632
    assert r.available is True


def test_solo_reacondicionado_muestra_los_dos_modos():
    raw = fixture_text("solotodo", "solo_reacondicionado.json")
    variants = st.parse_variants(raw, ref("143685"))
    assert [(v.variant_id, v.label, v.url) for v in variants] == [
        ("", "Solo nuevos: sin ofertas hoy", "https://www.solotodo.cl/products/143685"),
        (
            "todos",
            "Incluye reacondicionados y usados: $17.632 (1 tienda)",
            "https://www.solotodo.cl/products/143685?modo=todos",
        ),
    ]
    assert [v.selected for v in variants] == [True, False]


def test_nuevo_reacondicionado_usado_y_planes():
    # iPhone 15 Pro: 1 nuevo ($749.990), reacondicionados, un usado ($699.990) y
    # publicaciones con plan de Entel (se ignoran aunque sean más baratas que algunas).
    raw = fixture_text("solotodo", "nuevo_y_reacondicionado.json")
    assert st.parse(raw, ref("221836")).price == 749990
    assert st.parse(raw, ref("221836", "todos")).price == 699990
    labels = [v.label for v in st.parse_variants(raw, ref("221836"))]
    assert labels == [
        "Solo nuevos: $749.990 (1 tienda)",
        "Incluye reacondicionados y usados: $699.990 (4 tiendas)",
    ]


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        st.parse(fixture_text("solotodo", "no_encontrado.json"), ref("999999999"))


def _entity(
    price="1990.00", *, available=True, condition=NEW, cell_plan=None, bundle=None, currency=1
):
    return {
        "store": 1,
        "condition": condition,
        "cell_plan": cell_plan,
        "bundle": bundle,
        "currency": currency,
        "active_registry": {
            "is_available": available,
            "normal_price": "9990.00",
            "offer_price": price,
        },
    }


def _raw(entities, product_id=1, results=None):
    product = {"id": product_id, "name": "X", "picture_url": "https://x/y.webp"}
    if results is None:
        results = [{"product": {"id": product_id}, "entities": entities}]
    return json.dumps({"product": product, "available": {"results": results}})


def test_ignora_no_disponibles_planes_packs_y_otra_moneda():
    raw = _raw(
        [
            _entity("100.00", available=False),
            _entity("200.00", cell_plan={"name": "Plan"}),
            _entity("300.00", bundle={"name": "Pack"}),
            _entity("400.00", currency=2),
            _entity("0.00"),
            _entity(None),
            {"store": 9, "condition": NEW, "active_registry": None},
            _entity("17632.00"),
        ]
    )
    r = st.parse(raw, ref("1"))
    assert r.price == 17632
    assert r.list_price is None


def test_sin_entidades_es_agotado():
    r = st.parse(_raw([]), ref("1"))
    assert (r.price, r.available, r.title) == (None, False, "X")


def test_api_que_no_filtra_por_id_no_se_toma_como_agotado():
    # Con un id que no reconoce, available_entities devuelve todo el catálogo.
    others = [{"product": {"id": 342170}, "entities": [_entity("990.00")]}]
    with pytest.raises(FetchError):
        st.parse(_raw([], results=others), ref("1"))


def test_busca_su_resultado_entre_varios():
    results = [
        {"product": {"id": 2}, "entities": [_entity("100.00")]},
        {"product": {"id": 1}, "entities": [_entity("500.00")]},
    ]
    assert st.parse(_raw([], results=results), ref("1")).price == 500


def test_producto_distinto_es_fetch_error():
    with pytest.raises(FetchError):
        st.parse(_raw([], product_id=2), ref("1"))


@pytest.mark.parametrize(
    "raw",
    [
        "<html>mantención</html>",
        "[]",
        '{"product": {"id": 1}}',
        '{"product": {"id": 1}, "available": {"results": [{"product": {"id": 1}}]}}',
    ],
)
def test_respuesta_rota_es_fetch_error(raw):
    with pytest.raises(FetchError) as exc:
        st.parse(raw, ref("1"))
    assert not isinstance(exc.value, NotFoundError)


async def test_fetch_raw_junta_producto_y_entidades(monkeypatch):
    calls = []

    async def fake_get_text(url, **kwargs):
        calls.append((url, kwargs.get("params")))
        if "available_entities" in url:
            return json.dumps(
                {"results": [{"product": {"id": 1}, "entities": [_entity("1990.00")]}]}
            )
        return '{"id": 1, "name": "Cosa", "picture_url": null}'

    monkeypatch.setattr("tracker.processors.solotodo.get_text", fake_get_text)
    r = await st.fetch(ref("1"))
    assert calls == [
        ("https://publicapi.solotodo.com/products/1/", None),
        (
            "https://publicapi.solotodo.com/products/available_entities/",
            {"ids": "1", "countries": 1},
        ),
    ]
    assert (r.title, r.price, r.available) == ("Cosa", 1990, True)


@pytest.mark.parametrize(
    "url,mode",
    [
        ("https://www.solotodo.cl/products/265617", ""),
        ("https://www.solotodo.cl/products/265617-a-data-legend-860-2-tb-sleg-860-2000gcs", ""),
        ("https://solotodo.cl/products/265617/", ""),
        ("http://www.solotodo.cl/products/265617?utm_source=x#ofertas", ""),
        ("HTTPS://WWW.SOLOTODO.CL/products/265617-A-DATA", ""),
        ("  https://www.solotodo.cl/products/265617  ", ""),
        ("https://www.solotodo.cl/products/265617?modo=todos", "todos"),
        ("https://www.solotodo.cl/products/265617-slug?modo=TODOS&x=1", "todos"),
        ("https://www.solotodo.cl/products/265617?modo=otro", ""),
    ],
)
def test_normaliza_url(url, mode):
    assert st.matches(url)
    r = st.normalize(url)
    assert r.external_id == "265617"
    assert r.variant_id == mode
    suffix = "?modo=todos" if mode else ""
    assert r.canonical_url == f"https://www.solotodo.cl/products/265617{suffix}"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.solotodo.cl.evil.com/products/265617",
        "https://evilsolotodo.cl/products/265617",
        "https://www.solotodo.cl/",
        "https://www.solotodo.cl/products/",
        "https://www.solotodo.cl/products/abc",
        "https://www.solotodo.cl/notebooks",
        "https://www.solotodo.cl/search?search=ssd",
        "https://www.solotodo.cl/products/265617/otra",
        "https://publicapi.solotodo.com/products/265617/",
    ],
)
def test_no_matchea(url):
    assert not st.matches(url)
    with pytest.raises(ValueError):
        st.normalize(url)


def test_variant_label():
    assert st.variant_label("1", "") == "Solo nuevos"
    assert st.variant_label("1", "todos") == "Incluye reacondicionados y usados"


def test_modo_por_defecto_solo_cuenta_nuevos():
    raw = _raw(
        [
            _entity("100.00", condition=REFURB),
            _entity("200.00", condition="https://schema.org/UsedCondition"),
            _entity("300.00", condition=None),
            _entity("900.00"),
        ]
    )
    assert st.parse(raw, ref("1")).price == 900
    assert st.parse(raw, ref("1", "todos")).price == 100
