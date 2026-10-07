"""Tests del procesador de Salomon (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.salomon import SalomonProcessor

proc = SalomonProcessor()
URL = "https://salomon.cl/products/xt-6-protective"


def parse(fixture, url):
    return proc.parse(fixture_text("salomon", fixture), proc.normalize(url))


def test_tallas():
    r = parse("tallas.json", "https://salomon.cl/products/xt-6-protective")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "XT-6 PROTECTIVE (Castlerock / Black / Paloma / 4 UK)",
        199990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("salomon", "tallas.json")
    variantes = proc.parse_variants(
        raw, proc.normalize("https://salomon.cl/products/xt-6-protective")
    )
    assert len(variantes) == 32
    assert variantes[0].selected and variantes[0].variant_id == "67680217563502"
    assert variantes[0].label == "Castlerock / Black / Paloma / 4 UK: $199.990"
    assert sum("(agotada)" in v.label for v in variantes) == 7


def test_descuento():
    r = parse("descuento.json", "https://salomon.cl/products/chaqueta-outline-hd-insul-jkt")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "OUTLINE HD INSUL JKT (Rojo / S)",
        79996,
        199990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse("agotado.json", "https://salomon.cl/products/assassin")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "ASSASSIN (BLACK / WHITE / 162)",
        749990,
        None,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "xt-6-protective",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://salomon.cl/products/xt-6-protective",
        "https://www.salomon.cl/products/xt-6-protective",
        "http://salomon.cl/products/xt-6-protective/",
        "https://salomon.cl/products/XT-6-PROTECTIVE?utm_source=x#top",
        "https://salomon.cl/collections/hombre/products/xt-6-protective",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == ("xt-6-protective", URL, "")


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "salomon.cl"
    assert find_processor(URL).name == "salomon"
    assert not proc.matches("https://salomon.cl/")
    assert not proc.matches("https://salomon.cl/collections/hombre")
    assert not proc.matches("https://salomon.cl/search?q=polera")
    assert not proc.matches("https://salomon.cl/pages/tiendas")
    assert not proc.matches("https://salomon.cl.evil.com/products/xt-6-protective")
    assert not proc.matches("https://notsalomon.cl/products/xt-6-protective")
