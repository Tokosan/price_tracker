"""Tests del procesador de Fashion's Park (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.fashionspark import FashionsParkProcessor

proc = FashionsParkProcessor()
URL = "https://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601"


def parse(fixture, url):
    return proc.parse(fixture_text("fashionspark", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json", "https://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Polerón Niña Stitch Fucsia (Morado / 2)",
        12490,
        24990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("fashionspark", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize("https://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601"),
    )
    assert len(variantes) == 4
    assert variantes[0].selected and variantes[0].variant_id == "53173511618744"
    assert variantes[0].label == "Morado / 2: $12.490"
    assert sum("(agotada)" in v.label for v in variantes) == 1


def test_descuento():
    r = parse(
        "descuento.json", "https://fashionspark.com/products/pantalon-pitillo-nino-kaki-391021602"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Pantalón Pitillo Niño Kaki (Beige / 10)",
        9990,
        19990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://fashionspark.com/products/calcetin-hombre-pack10-basico-gris-melange-833050503",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Calcetín Hombre Pack10 Básico Gris Melange",
        4990,
        9990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "poleron-nina-stitch-fucsia-201088601",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601",
        "https://www.fashionspark.com/products/poleron-nina-stitch-fucsia-201088601",
        "http://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601/",
        "https://fashionspark.com/products/POLERON-NINA-STITCH-FUCSIA-201088601?utm_source=x#top",
        "https://fashionspark.com/collections/hombre/products/poleron-nina-stitch-fucsia-201088601",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "poleron-nina-stitch-fucsia-201088601",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "fashionspark.com"
    assert find_processor(URL).name == "fashionspark"
    assert not proc.matches("https://fashionspark.com/")
    assert not proc.matches("https://fashionspark.com/collections/hombre")
    assert not proc.matches("https://fashionspark.com/search?q=polera")
    assert not proc.matches("https://fashionspark.com/pages/tiendas")
    assert not proc.matches(
        "https://fashionspark.com.evil.com/products/poleron-nina-stitch-fucsia-201088601"
    )
    assert not proc.matches(
        "https://notfashionspark.com/products/poleron-nina-stitch-fucsia-201088601"
    )
