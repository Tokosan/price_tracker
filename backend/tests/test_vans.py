"""Tests del procesador de Vans (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.vans import VansProcessor

proc = VansProcessor()
URL = "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5"


def parse(fixture, url):
    return proc.parse(fixture_text("vans", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatilla Niño (1 A 4 Años) Knu Skool Café Vans (21)",
        29990,
        49990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("vans", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5"
        ),
    )
    assert len(variantes) == 6
    assert variantes[0].selected and variantes[0].variant_id == "45601805598918"
    assert variantes[0].label == "21: $29.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 5


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5?variant=45601805762758",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zapatilla Niño (1 A 4 Años) Knu Skool Café Vans (26.5)",
        29990,
        49990,
        True,
    )


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.vans.cl/products/zapatilla-unisex-ryland-ls-vans-vn000d49bzw-n12",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatilla Adulto Ryland Negro Vans (39)",
        32990,
        79990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
        "https://vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
        "http://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5/",
        "https://www.vans.cl/products/ZAPATILLA-NINO-KNU-SKOOL-ELASTIC-LA-VANS-VN000D0KFSB-WH5?utm_source=x#top",
        "https://www.vans.cl/collections/hombre/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.vans.cl"
    assert find_processor(URL).name == "vans"
    assert not proc.matches("https://www.vans.cl/")
    assert not proc.matches("https://www.vans.cl/collections/hombre")
    assert not proc.matches("https://www.vans.cl/search?q=polera")
    assert not proc.matches("https://www.vans.cl/pages/tiendas")
    assert not proc.matches(
        "https://vans.cl.evil.com/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5"
    )
    assert not proc.matches(
        "https://notvans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5"
    )
