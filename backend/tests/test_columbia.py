"""Tests del procesador de Columbia (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.columbia import ColumbiaProcessor

proc = ColumbiaProcessor()
URL = "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj"


def parse(fixture, url):
    return proc.parse(fixture_text("columbia", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json",
        "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polera Manga Larga Hombre Terminal Tackle Blanco Columbia (XS)",
        39992,
        49990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("columbia", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj"
        ),
    )
    assert len(variantes) == 6
    assert variantes[0].selected and variantes[0].variant_id == "51508947583272"
    assert variantes[0].label == "XS: $39.992 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 5


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj?variant=51409228038440",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polera Manga Larga Hombre Terminal Tackle Blanco Columbia (XXL)",
        39992,
        49990,
        True,
    )


def test_descuento():
    r = parse(
        "descuento.json",
        "https://www.columbiachile.cl/products/mochila-unisex-triple-canyon-36l-azul-columbia-2071541-ti3",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Mochila Unisex Triple Canyon 36L Azul Columbia",
        62495,
        124990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.columbiachile.cl/products/cortaviento-hombre-watertight-ii-jacket-columbia-1533891-4ok",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Cortaviento Hombre Watertight II Verde Stone Green Columbia (S)",
        80990,
        99990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
        "https://columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
        "http://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj/",
        "https://www.columbiachile.cl/products/POLERA-M-L-HOMBRE-TERMINAL-TACKLE-LS-S-COLUMBIA-1388261-7ZJ?utm_source=x#top",
        "https://www.columbiachile.cl/collections/hombre/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.columbiachile.cl"
    assert find_processor(URL).name == "columbia"
    assert not proc.matches("https://www.columbiachile.cl/")
    assert not proc.matches("https://www.columbiachile.cl/collections/hombre")
    assert not proc.matches("https://www.columbiachile.cl/search?q=polera")
    assert not proc.matches("https://www.columbiachile.cl/pages/tiendas")
    assert not proc.matches(
        "https://columbiachile.cl.evil.com/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj"
    )
    assert not proc.matches(
        "https://notcolumbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj"
    )
