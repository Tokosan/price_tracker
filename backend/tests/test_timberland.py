"""Timberland (base Fenicio). Fixtures reales sin `<script>`, `<style>` ni `<svg>`."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.timberland import TimberlandProcessor

timberland = TimberlandProcessor()
BASE = "https://www.timberland.cl/catalogo"
MID = f"{BASE}/zapatilla-mid-lace-up-hombre-em5_TB0A424R_EM5"
LOW = f"{BASE}/zapatilla-timb-low-lace-hombre-ejp_TB0A43NG_EJP"
BOAT = f"{BASE}/zapato-casual-boat-hombre-em6_TB0A4187_EM6"


def parse(fixture, url):
    return timberland.parse(fixture_text("timberland", fixture), timberland.normalize(url))


def test_cualquier_talla():
    r = parse("tallas.html", MID)
    assert r.title == "Zapatilla Mid Lace Up Hombre - Em5"
    assert (r.price, r.list_price, r.currency, r.available) == (129990, None, "CLP", True)
    assert r.image_url == (
        "https://f.fcdn.app/imgs/61e7c8/www.timberland.cl/timbcl/065f/original/catalogo/"
        "TB0A424R_EM5_1/1024-1024/zapatilla-mid-lace-up-hombre-em5.jpg"
    )


@pytest.mark.parametrize(("size", "available"), [("7", True), ("8", False), ("10.5", True)])
def test_talla_puntual(size, available):
    r = parse("tallas.html", f"{MID}?talla={size}")
    assert r.title == f"Zapatilla Mid Lace Up Hombre - Em5 (talla {size})"
    assert (r.price, r.available) == (129990, available)


def test_talla_que_ya_no_esta_es_agotada():
    r = parse("tallas.html", f"{MID}?talla=14")
    assert (r.price, r.available) == (129990, False)


def test_descuento():
    # $111.992, antes $139.990 (20 %); los relacionados también tienen descuentos.
    r = parse("descuento.html", LOW)
    assert r.title == "Zapatilla Timb Low Lace Hombre - Ejp"
    assert (r.price, r.list_price, r.available) == (111992, 139990, True)


def test_casi_agotado():
    # Solo queda la talla 8.
    assert parse("casi_agotado.html", BOAT).available is True
    assert parse("casi_agotado.html", f"{BOAT}?talla=8").available is True
    assert parse("casi_agotado.html", f"{BOAT}?talla=9").available is False


def test_todas_las_tallas_agotadas():
    raw = fixture_text("timberland", "casi_agotado.html").replace(
        'value="1:TB0A4187:EM6:8:1" data-cpre="8" data-stock="1"',
        'disabled value="1:TB0A4187:EM6:8:1" data-cpre="8" data-stock="0"',
    )
    r = timberland.parse(raw, timberland.normalize(BOAT))
    assert (r.price, r.available) == (119990, False)


def test_variantes_por_talla():
    raw = fixture_text("timberland", "tallas.html")
    variants = timberland.parse_variants(raw, timberland.normalize(MID))
    assert [v.label for v in variants] == [
        "Cualquier talla",
        "Talla 7",
        "Talla 8 (agotada)",
        "Talla 9",
        "Talla 10",
        "Talla 11",
        "Talla 7.5",
        "Talla 8.5 (agotada)",
        "Talla 9.5",
        "Talla 10.5",
    ]
    assert variants[0].selected and variants[0].url == MID
    assert variants[2].url == f"{MID}?talla=8"
    for v in variants:
        ref = timberland.normalize(v.url)
        assert (ref.external_id, ref.variant_id) == (v.external_id, v.variant_id)
    selected = timberland.parse_variants(raw, timberland.normalize(f"{MID}?talla=9"))[0]
    assert (selected.variant_id, selected.selected) == ("9", True)


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria.html", MID)


def test_ficha_de_otro_producto():
    with pytest.raises(FetchError):
        parse("tallas.html", LOW)


@pytest.mark.parametrize(
    ("url", "ext", "size", "canonical"),
    [
        (MID, "TB0A424R_EM5", "", MID),
        (f"{MID}/?utm_source=x#top", "TB0A424R_EM5", "", MID),
        (
            "http://timberland.cl/catalogo/x_tb0a424r_em5",
            "TB0A424R_EM5",
            "",
            f"{BASE}/x_TB0A424R_EM5",
        ),
        (f"{MID}?talla=9.5", "TB0A424R_EM5", "9.5", f"{MID}?talla=9.5"),
        (f"{BASE}/camisa_long_sleeve_TB0A6GRH590_4306", "TB0A6GRH590_4306", "", None),
    ],
)
def test_normaliza_url(url, ext, size, canonical):
    assert timberland.matches(url)
    ref = timberland.normalize(url)
    assert (ref.external_id, ref.variant_id) == (ext, size)
    if canonical:
        assert ref.canonical_url == canonical


@pytest.mark.parametrize(
    "url",
    [
        "https://www.timberland.cl.evil.com/catalogo/x_TB0A424R_EM5",
        "https://eviltimberland.cl/catalogo/x_TB0A424R_EM5",
        "https://www.timberland.cl/hombre",
        "https://www.timberland.cl/catalogo/zapatillas",
        "https://www.timberland.cl/catalogo/x_TB0A424R_EM5/otra",
        "https://www.timberland.com/catalogo/x_TB0A424R_EM5",
    ],
)
def test_no_matchea(url):
    assert not timberland.matches(url)


def test_registrado():
    assert find_processor(MID).name == "timberland"
