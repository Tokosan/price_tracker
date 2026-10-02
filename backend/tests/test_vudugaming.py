import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor, jumpseller
from tracker.processors.vudugaming import VuduGamingProcessor

vg = VuduGamingProcessor()
BASE = "https://www.vudugaming.cl"
SIERRA = f"{BASE}/sierra-west-espanol"


def parse(fixture, url):
    return vg.parse(fixture_text("vudugaming", fixture), vg.normalize(url))


def test_en_stock():
    r = parse("arknova_dados_en_stock.html", f"{BASE}/arknova-set-de-datos-magenta")
    assert (r.title, r.price, r.currency, r.available) == (
        "Arknova - Set de datos - Magenta",
        3990,
        "CLP",
        True,
    )
    assert r.list_price is None
    assert r.image_url


def test_descuento_trae_precio_final_y_precio_base():
    # Tema nuevo de Jumpseller: sin `#product-price.previous`; el original sale del meta
    # `product:original_price:amount`.
    r = parse("sierra_west_descuento.html", SIERRA)
    assert r.title == "Sierra West - Español"
    assert (r.price, r.list_price, r.available) == (31493, 44990, True)


def test_pagina_en_ingles_da_lo_mismo():
    es = parse("sierra_west_descuento.html", SIERRA)
    en = parse("sierra_west_descuento_en.html", f"{BASE}/en/sierra-west-espanol")
    assert en == es


def test_agotado():
    r = parse("marvel_united_agotado.html", f"{BASE}/marvel-united-x-men-espanol")
    assert (r.price, r.available) == (39990, False)


def test_preventa_abierta_esta_disponible():
    r = parse("nyakuza_preventa.html", f"{BASE}/preventa-nyakuza-espanol")
    assert (r.title, r.price, r.available) == ("Preventa - Nyakuza - Español", 34990, True)


BONE_WARS = f"{BASE}/bone-wars-espanol"


def test_no_disponible_aunque_el_json_ld_diga_instock():
    # Preventa cerrada: el JSON-LD dice InStock, pero el meta dice `pending` y la página
    # muestra "No disponible".
    raw = fixture_text("vudugaming", "bone_wars_no_disponible.html")
    assert "schema.org/InStock" in raw
    r = vg.parse(raw, vg.normalize(BONE_WARS))
    assert r.available is False


def test_preventa_con_reserva_usa_el_precio_total():
    # "MONTO PARA RESERVA": el JSON-LD y el meta traen el abono del 50 % ($41.495); se
    # sigue la variante "100%".
    raw = fixture_text("vudugaming", "bone_wars_no_disponible.html")
    assert 'content="41495.0"' in raw
    r = parse("bone_wars_no_disponible.html", BONE_WARS)
    assert (r.price, r.list_price) == (82990, None)


def test_reserva_sin_variante_100_toma_la_mas_cara():
    raw = fixture_text("vudugaming", "bone_wars_no_disponible.html").replace(
        '"name":"100%","option"', '"name":"Completo","option"'
    )
    r = vg.parse(raw, vg.normalize(BONE_WARS))
    assert r.price == 82990


def test_opcion_que_no_es_reserva_no_cambia_el_precio():
    raw = fixture_text("vudugaming", "bone_wars_no_disponible.html").replace(
        "MONTO PARA RESERVA", "COLOR"
    )
    r = vg.parse(raw, vg.normalize(BONE_WARS))
    assert r.price == 41495


def test_availability_desconocido_usa_el_json_ld(monkeypatch):
    # El logger se reemplaza: la config de logging de alembic (test_migrations) deshabilita
    # los loggers existentes y caplog no vería nada en la suite completa.
    avisos = []
    monkeypatch.setattr(jumpseller.log, "warning", lambda msg, *args: avisos.append(msg % args))
    raw = fixture_text("vudugaming", "arknova_dados_en_stock.html")
    raw = raw.replace(
        'product:availability" content="instock"', 'product:availability" content="raro"'
    )
    r = vg.parse(raw, vg.normalize(f"{BASE}/arknova-set-de-datos-magenta"))
    assert r.available is True
    assert len(avisos) == 1 and "'raro'" in avisos[0]


def test_sin_disponibilidad_es_fetch_error():
    raw = (
        '<meta property="og:type" content="product">'
        '<meta property="product:price:amount" content="12990.0">'
    )
    with pytest.raises(FetchError, match="disponibilidad"):
        vg.parse(raw, vg.normalize(SIERRA))


@pytest.mark.parametrize(
    ("fixture", "url"),
    [
        ("categoria_juegos_de_mesa.html", f"{BASE}/juegos-de-mesa"),
        ("home_en.html", f"{BASE}/en/juegos-de-mesa"),
    ],
)
def test_categoria_y_portada_se_rechazan(fixture, url):
    with pytest.raises(NotFoundError, match="no es una página de producto"):
        parse(fixture, url)


@pytest.mark.parametrize(
    "url",
    [
        SIERRA,
        "https://vudugaming.cl/Sierra-West-Espanol/",
        f"{BASE}/en/sierra-west-espanol",
        f"{BASE}/es/sierra-west-espanol/",
        f"{BASE}/en/sierra-west-espanol?srsltid=AfmBOoq1x2y3",
        "http://www.vudugaming.cl/sierra-west-espanol?utm_source=ig&utm_medium=social#fotos",
    ],
)
def test_normaliza_url(url):
    ref = vg.normalize(url)
    assert ref.external_id == "sierra-west-espanol"
    assert ref.canonical_url == SIERRA


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/",
        f"{BASE}/en/",
        f"{BASE}/en",
        f"{BASE}/en/?srsltid=AfmBOoq1x2y3",
        f"{BASE}/es",
        f"{BASE}/juegos-de-mesa/expansiones",
        f"{BASE}/en/juegos-de-mesa/expansiones",
        f"{BASE}/fr/sierra-west-espanol",
        "https://vudugaming.cl.evil.com/sierra-west-espanol",
        "https://evilvudugaming.cl/sierra-west-espanol",
    ],
)
def test_no_matchea(url):
    assert not vg.matches(url)
    with pytest.raises(ValueError):
        vg.normalize(url)


def test_find_processor():
    assert find_processor(SIERRA).name == "vudugaming"
    assert find_processor(f"{BASE}/en/sierra-west-espanol?srsltid=x").name == "vudugaming"
