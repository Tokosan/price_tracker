"""Decathlon: fixtures reales recortadas al payload RSC con el `itemGroup`.

Las fichas originales pesan ~0,5–1 MB. `tests/fixtures/decathlon/*.html` conservan solo
el `itemGroup` (partido en dos `self.__next_f.push`, para probar que el parser los junta)
y en cada talla se quitaron textos largos que el parser no usa (descripciones, ficha
técnica, imágenes extra, tiendas con stock, SKUs relacionados). `categoria.html` conserva
los primeros 20 KB del payload de una categoría.
"""

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.decathlon import DecathlonProcessor

decathlon = DecathlonProcessor()
POLERA = "https://www.decathlon.cl/p/polera-fitness-hombre-manga-corta-cuello-redondo/332540"
AZUL = f"{POLERA}/c43c344m8773498"
ZAPATOS = "https://www.decathlon.cl/p/zapatos-de-futbol-100-turf-tf-adulto/347845/c382m8808629"
MANCUERNAS = "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449/c1m8018574"
XL_AZUL = "64f812f0-6a22-4ea0-93c0-7e9e3ae27b00"
M_AZUL = "08e24265-1604-4b7a-b148-ec1989b689dc"
TALLA_42 = "a76e821f-a98e-4ae8-ad8e-ea92370333e0"


def parse(fixture, url):
    return decathlon.parse(fixture_text("decathlon", fixture), decathlon.normalize(url))


def test_producto_sin_tallas():
    r = parse("mancuernas.html", MANCUERNAS)
    assert r.title == "KIT MANCUERNAS 20 KG"
    assert (r.price, r.list_price, r.currency, r.available) == (60000, None, "CLP", True)
    assert r.image_url.startswith("https://contents.mediadecathlon.com/p3164513/")
    raw = fixture_text("decathlon", "mancuernas.html")
    assert decathlon.parse_variants(raw, decathlon.normalize(MANCUERNAS)) == []


def test_cualquier_talla_de_un_color():
    # Azul asfalto: S, M, L, 2XL con stock y XL agotada; todas a $10.000.
    r = parse("polera_tallas.html", AZUL)
    assert r.title == "POLERA FITNESS HOMBRE CUELLO REDONDO (Azul asfalto)"
    assert (r.price, r.list_price, r.available) == (10000, None, True)


def test_talla_con_stock_y_talla_agotada():
    r = parse("polera_tallas.html", f"{AZUL}?sku={M_AZUL}")
    assert r.title == "POLERA FITNESS HOMBRE CUELLO REDONDO (Azul asfalto, talla M)"
    assert (r.price, r.available) == (10000, True)
    r = parse("polera_tallas.html", f"{AZUL}?sku={XL_AZUL}")
    assert r.title == "POLERA FITNESS HOMBRE CUELLO REDONDO (Azul asfalto, talla XL)"
    assert (r.price, r.available) == (10000, False)


def test_talla_que_desaparece_es_agotado_sin_precio():
    r = parse("polera_tallas.html", f"{AZUL}?sku=00000000-0000-0000-0000-000000000000")
    assert (r.price, r.available) == (None, False)
    assert decathlon.sold_out_without_price is True


def test_otro_color_del_mismo_grupo_con_descuento():
    # Rosado pálido: fin de temporada (END_OF_LINE) a $6.000, antes $10.000.
    r = parse("polera_tallas.html", f"{POLERA}/c48m8842274")
    assert r.title == "POLERA FITNESS HOMBRE MANGA CORTA CUELLO REDONDO (rosado pálido)"
    assert (r.price, r.list_price, r.available) == (6000, 10000, True)


def test_descuento_por_talla():
    r = parse("zapatos_descuento.html", f"{ZAPATOS}?sku={TALLA_42}")
    assert r.title == "ZAPATOS DE FÚTBOL 100 TURF TF ADULTO (talla 42)"
    assert (r.price, r.list_price, r.available) == (9000, 20000, True)


def test_modelo_que_no_esta_en_la_ficha():
    # Un modelId inexistente redirige (200) al modelo por defecto del grupo.
    with pytest.raises(NotFoundError):
        parse("mancuernas.html", "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449/c1m9999999")


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria.html", MANCUERNAS)


def test_pagina_sin_payload():
    with pytest.raises(FetchError):
        decathlon.parse(
            "<html><body>Just a moment...</body></html>", decathlon.normalize(MANCUERNAS)
        )


def test_variantes_tallas_y_colores():
    raw = fixture_text("decathlon", "polera_tallas.html")
    variants = decathlon.parse_variants(raw, decathlon.normalize(AZUL))
    assert variants[0].selected and variants[0].variant_id == ""
    assert variants[0].label == "Cualquier talla (Azul asfalto): desde $10.000"
    sizes = [v for v in variants if v.variant_id]
    assert [v.label for v in sizes] == [
        "Talla S: $10.000",
        "Talla M: $10.000",
        "Talla L: $10.000",
        "Talla XL: $10.000 (agotada)",
        "Talla 2XL: $10.000",
    ]
    colors = [v for v in variants if v.external_id != "8773498"]
    assert len(colors) == 5
    rosado = next(v for v in colors if v.external_id == "8842274")
    assert rosado.label == "Color rosado pálido: desde $6.000"
    assert rosado.url == f"{POLERA}/c48m8842274"
    for v in variants:
        ref = decathlon.normalize(v.url)
        assert (ref.external_id, ref.variant_id) == (v.external_id, v.variant_id)


@pytest.mark.parametrize(
    ("url", "model", "sku", "canonical"),
    [
        (MANCUERNAS, "8018574", "", MANCUERNAS),
        (f"{MANCUERNAS}/?utm_source=x#top", "8018574", "", MANCUERNAS),
        (
            "http://decathlon.cl/p/Kit-Mancuernas-20-KG/7449/m8018574",
            "8018574",
            "",
            "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449/m8018574",
        ),
        (f"{AZUL}?sku={M_AZUL.upper()}", "8773498", M_AZUL, f"{AZUL}?sku={M_AZUL}"),
        (f"{AZUL}?sku=no-es-un-uuid", "8773498", "", AZUL),
    ],
)
def test_normaliza_url(url, model, sku, canonical):
    assert decathlon.matches(url)
    ref = decathlon.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (model, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.decathlon.cl.evil.com/p/kit-mancuernas-20-kg/7449/c1m8018574",
        "https://evildecathlon.cl/p/kit-mancuernas-20-kg/7449/c1m8018574",
        "https://www.decathlon.cl/deportes/fitness/mancuernas",
        "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449",
        "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449/c1",
        "https://www.decathlon.com/p/kit-mancuernas-20-kg/7449/c1m8018574",
    ],
)
def test_no_matchea(url):
    assert not decathlon.matches(url)


def test_registrado():
    assert find_processor(MANCUERNAS).name == "decathlon"
