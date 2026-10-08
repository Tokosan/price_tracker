"""Saxoline: JSON real de la ficha de Shopify, pedido al dominio del checkout (front headless)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.saxoline import SaxolineProcessor

sax = SaxolineProcessor()
BANANO = "https://saxoline.cl/products/banano-wesley-negro"
DINO = "https://saxoline.cl/products/mochila-dream-rider-dino"


def parse(fixture, url):
    return sax.parse(fixture_text("saxoline", fixture), sax.normalize(url))


def test_descuento():
    r = parse("descuento.json", BANANO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Banano Wesley negro",
        5990,
        12990,
        "CLP",
        True,
    )


def test_sin_descuento():
    r = parse("sin_descuento.json", DINO)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Mochila Dream Rider Dino",
        25990,
        None,
        True,
    )


async def test_pide_el_js_al_checkout(monkeypatch):
    pedidas = []

    async def fake_get_text(url, **kwargs):
        pedidas.append(url)
        return fixture_text("saxoline", "descuento.json")

    monkeypatch.setattr("tracker.processors.shopify.get_text", fake_get_text)
    await sax.fetch(sax.normalize(BANANO))
    assert pedidas == ["https://checkout.saxoline.cl/products/banano-wesley-negro.js"]


@pytest.mark.parametrize(
    "url",
    [
        "https://saxoline.cl.evil.com/products/banano-wesley-negro",
        "https://saxoline.cl/collections/x",
    ],
)
def test_no_matchea(url):
    assert not sax.matches(url)


def test_registrado():
    assert find_processor(BANANO).name == "saxoline"
