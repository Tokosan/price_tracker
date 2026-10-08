"""Puma: fichas HTML reales (Magento 2, tema propio), con el `form_key` redactado."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.puma import PumaProcessor

puma = PumaProcessor()
S = "https://cl.puma.com"
SUEDE = f"{S}/zapatillas-suede-xl-para-ninos-396578-55.html"
POLERON = f"{S}/poleron-con-capucha-y-cierre-pumatech-para-hombre-634415-01.html"
GORRO = f"{S}/gorro-con-visera-premium-essentials-classic-025974-02.html"


def parse(fixture, url):
    return puma.parse(fixture_text("puma", fixture), puma.normalize(url))


def test_cualquier_talla_con_descuento():
    r = parse("suede_tallas_descuento.html", SUEDE)
    assert r.title == "Zapatillas Suede XL para niños (Shadow Gray-Lemon Meringue)"
    assert (r.price, r.list_price, r.currency, r.available) == (32990, 54990, "CLP", True)
    assert r.image_url.startswith("https://images.puma.com/image/upload/")
    assert "/396578/55/" in r.image_url


def test_talla_con_stock_y_talla_agotada():
    r = parse("suede_tallas_descuento.html", f"{SUEDE}?sku=4069161419744")
    assert r.title == (
        "Zapatillas Suede XL para niños (Shadow Gray-Lemon Meringue, talla 31 CL / 1 US (19 CM))"
    )
    assert (r.price, r.list_price, r.available) == (32990, 54990, True)
    r = parse("suede_tallas_descuento.html", f"{SUEDE}?sku=4069161419812")
    assert r.title.endswith("talla 32.5 CL / 1.5 US (19.5 CM))")
    assert (r.price, r.available) == (None, False)
    assert puma.sold_out_without_price is True


def test_talla_que_no_esta_es_agotado():
    r = parse("suede_tallas_descuento.html", f"{SUEDE}?sku=4000000000000")
    assert r.title == "Zapatillas Suede XL para niños (Shadow Gray-Lemon Meringue)"
    assert (r.price, r.available) == (None, False)


def test_sin_descuento_y_variantes_con_agotadas():
    r = parse("poleron_talla_agotada.html", POLERON)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Polerón con capucha y cierre PUMATECH para hombre (Puma Black)",
        69990,
        None,
        True,
    )
    raw = fixture_text("puma", "poleron_talla_agotada.html")
    variants = puma.parse_variants(raw, puma.normalize(POLERON))
    assert [v.label for v in variants[:4]] == [
        "Cualquier talla",
        "Talla XS (agotada)",
        "Talla S: $69.990",
        "Talla M: $69.990",
    ]
    for v in variants:
        ref = puma.normalize(v.url)
        assert (ref.external_id, ref.variant_id) == (v.external_id, v.variant_id)


def test_talla_unica_sin_selector():
    r = parse("gorro_talla_unica.html", GORRO)
    assert (r.title, r.price, r.list_price, r.available) == (
        "Gorro con visera Premium Essentials Classic (Puma White)",
        11990,
        14990,
        True,
    )
    raw = fixture_text("puma", "gorro_talla_unica.html")
    assert puma.parse_variants(raw, puma.normalize(GORRO)) == []


def test_ficha_de_otro_color_es_error():
    # La ficha del color 02 leída como si fuera el 04.
    with pytest.raises(FetchError):
        parse("gorro_talla_unica.html", GORRO.replace("-02.html", "-04.html"))


def test_sin_spconfig_es_error():
    raw = fixture_text("puma", "gorro_talla_unica.html").replace('"spConfig":', '"otro":')
    with pytest.raises(FetchError):
        puma.parse(raw, puma.normalize(GORRO))


def test_no_es_producto():
    with pytest.raises(NotFoundError):
        puma.parse("<html><title>Hombres</title></html>", puma.normalize(GORRO))


async def test_color_despublicado_es_agotado(monkeypatch):
    estilo = fixture_text("puma", "poleron_talla_agotada.html")
    pedidas = []

    async def fake_get_text(url, **kwargs):
        pedidas.append(url)
        if url.endswith("-634415-03.html"):
            raise NotFoundError(f"404 en {url}")
        return estilo

    monkeypatch.setattr("tracker.processors.puma.get_text", fake_get_text)
    ref = puma.normalize(POLERON.replace("-01.html", "-03.html"))
    r = await puma.fetch(ref)
    assert (r.title, r.price, r.available) == ("", None, False)
    assert pedidas[-1] == f"{S}/poleron-con-capucha-y-cierre-pumatech-para-hombre-634415.html"


async def test_estilo_inexistente_sigue_siendo_404(monkeypatch):
    async def fake_get_text(url, **kwargs):
        raise NotFoundError(f"404 en {url}")

    monkeypatch.setattr("tracker.processors.puma.get_text", fake_get_text)
    with pytest.raises(NotFoundError):
        await puma.fetch(puma.normalize(POLERON))


@pytest.mark.parametrize(
    ("url", "external_id", "sku", "canonical"),
    [
        (SUEDE, "396578_55", "", SUEDE),
        (
            "http://CL.PUMA.COM/Zapatillas-Suede-XL-para-Ninos-396578-55.html#x",
            "396578_55",
            "",
            SUEDE,
        ),
        (f"{SUEDE}?sku=4069161419744", "396578_55", "4069161419744", f"{SUEDE}?sku=4069161419744"),
        (f"{SUEDE}?sku=abc", "396578_55", "", SUEDE),
    ],
)
def test_normaliza_url(url, external_id, sku, canonical):
    assert puma.matches(url)
    ref = puma.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (external_id, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://cl.puma.com.evil.com/zapatillas-suede-xl-para-ninos-396578-55.html",
        "https://evilcl.puma.com/zapatillas-suede-xl-para-ninos-396578-55.html",
        "https://cl.puma.com/hombres.html",
        "https://cl.puma.com/poleron-con-capucha-y-cierre-pumatech-para-hombre-634415.html",
        "https://us.puma.com/zapatillas-suede-xl-para-ninos-396578-55.html",
    ],
)
def test_no_matchea(url):
    assert not puma.matches(url)


def test_registrado():
    assert find_processor(SUEDE).name == "puma"
