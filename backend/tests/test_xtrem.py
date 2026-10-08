"""Xtrem: JSON real de la ficha de Shopify, pedido al dominio del checkout (front headless)."""

import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.xtrem import XtremProcessor

xtrem = XtremProcessor()
LOGAN = "https://xtrem.cl/products/mochila-escolar-logan-conejo"
KIRA = "https://xtrem.cl/products/mochila-notebook-15-kira-verde-menta"


def parse(fixture, url):
    return xtrem.parse(fixture_text("xtrem", fixture), xtrem.normalize(url))


def test_descuento():
    r = parse("descuento.json", LOGAN)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Mochila escolar Logan conejo",
        20990,
        25990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://cdn.shopify.com/")


def test_sin_descuento():
    r = parse("sin_descuento.json", KIRA)
    assert (r.title, r.price, r.list_price, r.available) == (
        'Mochila para notebook 15" Kira verde menta',
        32990,
        None,
        True,
    )


def test_agotado():
    data = json.loads(fixture_text("xtrem", "descuento.json"))
    data["variants"][0]["available"] = False
    r = xtrem.parse(json.dumps(data), xtrem.normalize(LOGAN))
    assert (r.price, r.available) == (20990, False)


async def test_pide_el_js_al_checkout(monkeypatch):
    pedidas = []

    async def fake_get_text(url, **kwargs):
        pedidas.append(url)
        return fixture_text("xtrem", "descuento.json")

    monkeypatch.setattr("tracker.processors.shopify.get_text", fake_get_text)
    await xtrem.fetch(
        xtrem.normalize(f"https://www.xtrem.cl/collections/mochilas/products/{LOGAN[26:]}")
    )
    assert pedidas == ["https://checkout.xtrem.cl/products/mochila-escolar-logan-conejo.js"]


@pytest.mark.parametrize(
    "url",
    [
        "https://xtrem.cl.evil.com/products/mochila-escolar-logan-conejo",
        "https://xtrem.cl/collections/mochilas",
        "https://checkout.xtrem.cl/products/mochila-escolar-logan-conejo",
    ],
)
def test_no_matchea(url):
    assert not xtrem.matches(url)


def test_registrado():
    assert find_processor(LOGAN).name == "xtrem"
    assert xtrem.normalize(f"{LOGAN}?variant=1").canonical_url == LOGAN
