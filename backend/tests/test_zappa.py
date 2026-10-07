"""Zappa (PrestaShop con tallas). Fixtures reales sin `<script>` (salvo JSON-LD), estilos ni
SVG, con el token de PrestaShop del formulario de compra redactado (`REDACTED`)."""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.zappa import ZappaProcessor

zappa = ZappaProcessor()
ZAPATO = "https://www.zappa.cl/producto/zapatos-mujer-cuero/25588-zapato-cuero-mujer-zam0223a01v0107.html"
SANDALIA = (
    "https://www.zappa.cl/producto/sandalias-mujer/13783-Sandalia-Casual-ZAPPA-zam0001a05v0103.html"
)


def parse(fixture, url):
    return zappa.parse(fixture_text("zappa", fixture), zappa.normalize(url))


def test_cualquier_talla_con_descuento():
    # $52.990 con rebaja de $27.000 sobre $79.990 (price_without_reduction).
    r = parse("descuento_tallas.html", ZAPATO)
    assert r.title == "Zapato Cuero Mujer"
    assert (r.price, r.list_price, r.currency, r.available) == (52990, 79990, "CLP", True)
    assert r.image_url == "https://www.zappa.cl/194809-thickbox_default/zapato-cuero-mujer.jpg"


@pytest.mark.parametrize(
    ("fragment", "name", "available"),
    [
        ("#/3-talla-36", "36", True),
        ("#/2-talla-35", "35", False),
        ("#/13-color-beige/7-talla-40", "40", True),
    ],
)
def test_talla_puntual(fragment, name, available):
    r = parse("descuento_tallas.html", f"{ZAPATO}{fragment}")
    assert r.title == f"Zapato Cuero Mujer (talla {name})"
    assert (r.price, r.available) == (52990, available)


def test_tallas_agotadas_en_otra_ficha():
    assert parse("sandalia.html", f"{SANDALIA}#/5-talla-38").available is False
    r = parse("sandalia.html", SANDALIA)
    assert (r.price, r.list_price, r.available) == (27990, 59990, True)


def test_todas_las_tallas_agotadas():
    raw = fixture_text("zappa", "sandalia.html").replace(
        "&quot;available&quot;:true", "&quot;available&quot;:false"
    )
    r = zappa.parse(raw, zappa.normalize(SANDALIA))
    assert (r.price, r.available) == (27990, False)


def test_variantes_por_talla():
    raw = fixture_text("zappa", "descuento_tallas.html")
    variants = zappa.parse_variants(raw, zappa.normalize(ZAPATO))
    assert [v.label for v in variants] == [
        "Cualquier talla",
        "Talla 35 (agotada)",
        "Talla 36",
        "Talla 37",
        "Talla 38",
        "Talla 39",
        "Talla 40",
    ]
    assert variants[0].selected and variants[0].url == ZAPATO
    assert variants[2].url == f"{ZAPATO}#/3-talla-36"
    for v in variants:
        ref = zappa.normalize(v.url)
        assert (ref.external_id, ref.variant_id, ref.canonical_url) == (
            v.external_id,
            v.variant_id,
            v.url,
        )


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria.html", ZAPATO)


def test_ficha_de_otro_producto():
    with pytest.raises(FetchError):
        parse("sandalia.html", ZAPATO)


@pytest.mark.parametrize(
    ("url", "pid", "size", "canonical"),
    [
        (ZAPATO, "25588", "", ZAPATO),
        (f"{ZAPATO}?utm=x", "25588", "", ZAPATO),
        (
            "https://zappa.cl/producto/zapatos-mujer-cuero/25588-139561-zapato-cuero-mujer-zam0223a01v0107.html#/13-color-beige/3-talla-36",
            "25588",
            "3",
            "https://www.zappa.cl/producto/zapatos-mujer-cuero/25588-139561-zapato-cuero-mujer-zam0223a01v0107.html#/3-talla-36",
        ),
    ],
)
def test_normaliza_url(url, pid, size, canonical):
    assert zappa.matches(url)
    ref = zappa.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (pid, size, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.zappa.cl.evil.com/producto/sandalias-mujer/13783-sandalia.html",
        "https://evilzappa.cl/producto/sandalias-mujer/13783-sandalia.html",
        "https://www.zappa.cl/12-sandalias-mujer",
        "https://www.zappa.cl/content/1-entrega",
    ],
)
def test_no_matchea(url):
    assert not zappa.matches(url)


def test_registrado():
    assert find_processor(ZAPATO).name == "zappa"
