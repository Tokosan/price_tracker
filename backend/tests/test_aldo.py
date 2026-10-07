import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.aldo import AldoProcessor

aldo = AldoProcessor()
BASE = "https://www.aldo.cl/aldo-cl/product"
FINESPEC = f"{BASE}/15933076/Finespec-Zapatilla-Urbana-Hombre-Negra-Aldo"
BRUNETTE = f"{BASE}/17349756/Brunette-Zapato-formal-Mujer-Cuero-Negro-Aldo"


def parse(fixture, url):
    return aldo.parse(fixture_text("aldo", fixture), aldo.normalize(url))


def test_talla_con_descuento():
    # Internet $34.990, normal tachado $69.900; vendedor FALABELLA.
    r = parse("zapatilla_descuento.json", f"{FINESPEC}/15933079")
    assert r.title == "Finespec Zapatilla Urbana Hombre Negra Aldo (42 CL)"
    assert (r.price, r.list_price, r.currency, r.available) == (34990, 69900, "CLP", True)
    assert r.image_url == "https://media.falabella.com/falabellaCL/15933079_1/public"


def test_talla_agotada():
    r = parse("zapato_tallas.json", f"{BRUNETTE}/17349757")
    assert r.title == "Brunette Zapato formal Mujer Cuero Negro Aldo (36 CL)"
    assert (r.price, r.list_price, r.available) == (39990, 79900, False)


def test_variantes_por_talla():
    raw = fixture_text("aldo", "zapato_tallas.json")
    variants = aldo.parse_variants(raw, aldo.normalize(BRUNETTE))
    assert len(variants) == 8
    assert variants[0].selected and variants[0].label == "37 CL: $39.990"
    assert variants[0].url == f"{BRUNETTE}/17349758"
    by_sku = {v.variant_id: v for v in variants}
    assert by_sku["17349757"].label == "36 CL: $39.990 (agotada)"
    for v in variants:
        assert aldo.normalize(v.url).variant_id == v.variant_id


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("no_encontrado.json", f"{BASE}/999999999")


@pytest.mark.parametrize(
    ("url", "pid", "sku", "canonical"),
    [
        (FINESPEC, "15933076", "", FINESPEC),
        (f"{FINESPEC}/15933079?x=1#y", "15933076", "15933079", f"{FINESPEC}/15933079"),
        ("https://aldo.cl/aldo-cl/product/15933076", "15933076", "", f"{BASE}/15933076"),
    ],
)
def test_normaliza_url(url, pid, sku, canonical):
    assert aldo.matches(url)
    ref = aldo.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (pid, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.aldo.cl.evil.com/aldo-cl/product/15933076",
        "https://evilaldo.cl/aldo-cl/product/15933076",
        "https://www.aldo.cl/aldo-cl/category/cat1720006/Zapatos-Hombre",
        "https://www.aldo.cl/aldo-cl/collection/sale-aldo",
        "https://www.aldo.cl/falabella-cl/product/15933076",
        "https://www.falabella.com/aldo-cl/product/15933076",
    ],
)
def test_no_matchea(url):
    assert not aldo.matches(url)


def test_registrado_sin_chocar_con_falabella():
    assert find_processor(FINESPEC).name == "aldo"
    assert find_processor("https://www.falabella.com/falabella-cl/product/80758957").name == (
        "falabella"
    )


async def test_fetch_pide_la_api_de_falabella_con_site_aldo(monkeypatch):
    calls = []

    async def fake_get_text(url, *, params=None):
        calls.append((url, list(params.items())))
        return "{}"

    monkeypatch.setattr("tracker.processors.falabella_platform.get_text", fake_get_text)
    await aldo.fetch_raw(aldo.normalize(FINESPEC))
    assert calls == [
        (
            "https://www.falabella.com/s/browse/v3/product/cl",
            [("site", "aldo-cl"), ("productId", "15933076")],
        )
    ]
