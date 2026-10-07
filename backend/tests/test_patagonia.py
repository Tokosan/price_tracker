"""Tests del procesador de Patagonia (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.patagonia import PatagoniaProcessor

proc = PatagoniaProcessor()
URL = "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado"


def parse(fixture, url):
    return proc.parse(fixture_text("patagonia", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polar de niña Los Gatos Polerón- Usado (BLANCO_(BCW) / XS / Detalles de uso)",
        26000,
        None,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("patagonia", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado"
        ),
    )
    assert len(variantes) == 11
    assert variantes[0].selected and variantes[0].variant_id == "51819337449653"
    assert variantes[0].label == "BLANCO_(BCW) / XS / Detalles de uso: $26.000 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 8


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado?variant=52679354843317",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polar de niña Los Gatos Polerón- Usado (BLANCO_(BCW) / S / Detalles de uso)",
        26000,
        None,
        True,
    )


def test_agotado():
    r = parse("agotado.json", "https://cl.patagonia.com/products/vest-mujer-bivy-hooded-vest-usado")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Vest Mujer Bivy Hooded Vest - Usado (AZUL_(SBDP) / S / Detalles de uso)",
        48000,
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
        "65485-polar-de-nina-los-gatos-poleron-usado",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado",
        "http://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado/",
        "https://cl.patagonia.com/products/65485-POLAR-DE-NINA-LOS-GATOS-POLERON-USADO?utm_source=x#top",
        "https://cl.patagonia.com/collections/hombre/products/65485-polar-de-nina-los-gatos-poleron-usado",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "65485-polar-de-nina-los-gatos-poleron-usado",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "cl.patagonia.com"
    assert find_processor(URL).name == "patagonia"
    assert not proc.matches("https://cl.patagonia.com/")
    assert not proc.matches("https://cl.patagonia.com/collections/hombre")
    assert not proc.matches("https://cl.patagonia.com/search?q=polera")
    assert not proc.matches("https://cl.patagonia.com/pages/tiendas")
    assert not proc.matches(
        "https://cl.patagonia.com.evil.com/products/65485-polar-de-nina-los-gatos-poleron-usado"
    )
    assert not proc.matches(
        "https://notcl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado"
    )
