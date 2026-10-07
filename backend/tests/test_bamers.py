"""Tests del procesador de Bamers (Shopify, fixtures reales de `/products/<handle>.js`)."""

from datetime import timedelta

import pytest

from tests.conftest import fixture_text
from tracker.processors import find_processor
from tracker.processors.bamers import BamersProcessor

proc = BamersProcessor()
URL = "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"


def parse(fixture, url):
    return proc.parse(fixture_text("bamers", fixture), proc.normalize(url))


def test_tallas():
    r = parse(
        "tallas.json", "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zapatillas Niña Knit Flex Rosado (CL 20)",
        9990,
        24990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tallas_se_eligen_al_agregar():
    raw = fixture_text("bamers", "tallas.json")
    variantes = proc.parse_variants(
        raw,
        proc.normalize(
            "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"
        ),
    )
    assert len(variantes) == 5
    assert variantes[0].selected and variantes[0].variant_id == "64643855778163"
    assert variantes[0].label == "CL 20: $9.990 (agotada)"
    assert sum("(agotada)" in v.label for v in variantes) == 1


def test_talla_con_stock():
    r = parse(
        "tallas.json",
        "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851?variant=64643855810931",
    )
    assert (r.title, r.price, r.list_price, r.available) == (
        "Zapatillas Niña Knit Flex Rosado (CL 21)",
        9990,
        24990,
        True,
    )


def test_descuento():
    r = parse(
        "descuento.json",
        "https://www.bamers.cl/products/zuecos-eva-mujer-airline-high-rosa-metalico-bmwcl0364mrs5",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Zuecos EVA Mujer Airline High Rosa Metálico (CL 35)",
        19995,
        39990,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://")


def test_agotado():
    r = parse(
        "agotado.json",
        "https://www.bamers.cl/products/pantuflas-mujer-piamonte-leather-b-leopardo-bmwss0753blew26",
    )
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Pantuflas Mujer Piamonte Leather B Leopardo (CL 35)",
        19990,
        49990,
        "CLP",
        False,
    )
    assert r.image_url.startswith("https://")


def test_tienda_de_ropa_con_selector_de_tallas():
    assert proc.supports_variants
    assert proc.check_interval == timedelta(hours=12)
    ref = proc.normalize(f"{URL}?variant=123")
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
        "zapatillas-nina-knit-flex-rosado-bmgsn081851",
        "123",
        f"{URL}?variant=123",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851",
        "https://bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851",
        "http://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851/",
        "https://www.bamers.cl/products/ZAPATILLAS-NINA-KNIT-FLEX-ROSADO-BMGSN081851?utm_source=x#top",
        "https://www.bamers.cl/collections/hombre/products/zapatillas-nina-knit-flex-rosado-bmgsn081851",
    ],
)
def test_normaliza_url(url):
    ref = proc.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "zapatillas-nina-knit-flex-rosado-bmgsn081851",
        URL,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert proc.domain() == "www.bamers.cl"
    assert find_processor(URL).name == "bamers"
    assert not proc.matches("https://www.bamers.cl/")
    assert not proc.matches("https://www.bamers.cl/collections/hombre")
    assert not proc.matches("https://www.bamers.cl/search?q=polera")
    assert not proc.matches("https://www.bamers.cl/pages/tiendas")
    assert not proc.matches(
        "https://bamers.cl.evil.com/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"
    )
    assert not proc.matches(
        "https://notbamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"
    )
