"""Tests del procesador de Street Machine (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.streetmachine import StreetMachineProcessor

proc = StreetMachineProcessor()
URL = "https://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl"


def parse(fixture, url):
    return proc.parse(fixture_text("streetmachine", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json", "https://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polera Reef Men Sirena Blanco (Blanco / S)",
        16990,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("streetmachine", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl"
        ),
    )
    assert len(variantes) == 4
    assert variantes[0].selected and variantes[0].variant_id == "47175654867117"
    assert variantes[0].label == "Blanco / S: $16.990"
    assert sum("(agotada)" in v.label for v in variantes) == 3


def test_descuento():
    r = parse(
        "descuento.json",
        "https://www.streetmachine.cl/products/palmer-all-gender-washed-black-a545d22palwsb",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Stance Sock Unisex Palmer all gender washed blk",
        8994,
        14990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.streetmachine.cl/products/bolsa-algodon-whatup-totewhatupgrande",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "BOLSA ALGODON WHATUP",
        6990,
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
        "polera-reef-pv2719blancl-rfmpov2719bl",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl",
        "https://streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl",
        "http://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl/",
        "https://www.streetmachine.cl/products/POLERA-REEF-PV2719BLANCL-RFMPOV2719BL?utm_source=x#top",
        "https://www.streetmachine.cl/collections/hombre/products/polera-reef-pv2719blancl-rfmpov2719bl",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "polera-reef-pv2719blancl-rfmpov2719bl",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.streetmachine.cl"
    assert find_processor(URL).name == "streetmachine"
    assert not proc.matches("https://www.streetmachine.cl/")
    assert not proc.matches("https://www.streetmachine.cl/collections/hombre")
    assert not proc.matches("https://www.streetmachine.cl/search?q=polera")
    assert not proc.matches("https://www.streetmachine.cl/pages/tiendas")
    assert not proc.matches(
        "https://streetmachine.cl.evil.com/products/polera-reef-pv2719blancl-rfmpov2719bl"
    )
    assert not proc.matches(
        "https://notstreetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl"
    )
