import pytest

from tests.conftest import fixture_text
from tracker.processors import PROCESSORS, FetchError, NotFoundError, find_processor
from tracker.processors.buscalibre import BuscalibreProcessor

bl = BuscalibreProcessor()

HAIL_MARY = "https://www.buscalibre.cl/libro-proyecto-hail-mary/9789566190448/p/62884122"
IMPORTADO = "https://www.buscalibre.cl/libro-project-hail-mary-a-novel/9780593135204/p/53298535"
PREVENTA = (
    "https://www.buscalibre.cl/libro-estuche-habitos-atomicos-habitos-atomicos-en-accion/"
    "9788411193788/p/68642036"
)
AGOTADO = (
    "https://www.buscalibre.cl/libro-introduction-to-chemical-physics-designed-for-the-use-of-"
    "academies-high-schools-and-colleges/9781143433078/p/20000111"
)
AUDIOLIBRO = "https://www.buscalibre.cl/libro-digital-habitos-atomicos/9788411191203/p/63595406"


def parse(fixture, url):
    return bl.parse(fixture_text("buscalibre", fixture), bl.normalize(url))


def test_esta_registrado():
    assert PROCESSORS["buscalibre"].label == "Buscalibre"
    assert find_processor(HAIL_MARY).name == "buscalibre"
    assert bl.sold_out_without_price is True


def test_descuento_solo_cuenta_el_nuevo():
    # Nuevo $20.700 (antes $23.000) y un usado de un tercero a $13.800.
    r = parse("descuento_y_usado.html", HAIL_MARY)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Proyecto Hail Mary",
        20700,
        23000,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://images.cdn3.buscalibre.com/")


def test_modo_todos_incluye_el_usado():
    # El tachado del usado ($5.800) es menor que su precio: no es un precio "antes".
    r = parse("descuento_y_usado.html", HAIL_MARY + "?modo=todos")
    assert (r.price, r.list_price, r.available) == (13800, None, True)


def test_variantes_ofrece_los_dos_modos():
    raw = fixture_text("buscalibre", "descuento_y_usado.html")
    variants = bl.parse_variants(raw, bl.normalize(HAIL_MARY))
    assert [(v.variant_id, v.label, v.selected, v.url) for v in variants] == [
        ("", "Solo nuevos: $20.700", True, HAIL_MARY),
        ("todos", "Incluye usados: $13.800", False, HAIL_MARY + "?modo=todos"),
    ]


def test_sin_usados_ofrece_un_solo_modo():
    raw = fixture_text("buscalibre", "importado_eeuu.html")
    variants = bl.parse_variants(raw, bl.normalize(IMPORTADO))
    assert [v.variant_id for v in variants] == [""]
    # Pero si el link pide "todos", ese modo aparece igual.
    variants = bl.parse_variants(raw, bl.normalize(IMPORTADO + "?modo=todos"))
    assert [(v.variant_id, v.selected) for v in variants] == [("", False), ("todos", True)]


def replaced(fixture: str, old: str, new: str) -> str:
    raw = fixture_text("buscalibre", fixture)
    assert old in raw, old
    return raw.replace(old, new)


def test_importado_cuenta_como_disponible_sin_precio_antes():
    # "Origen: Estados Unidos", llega en un mes. La tienda tacha $65.240, pero en un
    # importado es una fórmula (~2× el precio), no un precio normal real.
    raw = fixture_text("buscalibre", "importado_eeuu.html")
    assert "&quot;importacion&quot;: 1" in raw and "$ 65.240" in raw
    r = bl.parse(raw, bl.normalize(IMPORTADO))
    assert r.title == "Project Hail Mary: A Novel (en Inglés)"
    assert (r.price, r.list_price, r.available) == (35880, None, True)


def test_preventa_importada_cuenta_como_disponible_sin_precio_antes():
    # Preventa desde España: tachado $114.050 (el doble), que no se guarda.
    r = parse("preventa_importado.html", PREVENTA)
    assert (r.price, r.list_price, r.available) == (57030, None, True)


def test_audiolibro_sin_descuento():
    # El tachado es igual al precio: no hay precio "antes".
    r = parse("audiolibro_sin_descuento.html", AUDIOLIBRO)
    assert (r.price, r.list_price, r.available) == (24900, None, True)


def test_agotado_sin_precio():
    r = parse("agotado.html", AGOTADO)
    assert r.title.startswith("introduction to chemical physics")
    assert (r.price, r.list_price, r.available) == (None, None, False)
    assert (
        bl.parse_variants(fixture_text("buscalibre", "agotado.html"), bl.normalize(AGOTADO)) == []
    )


def test_sin_opciones_ni_marca_de_agotado_es_error_de_lectura():
    raw = replaced("agotado.html", 'id="noti-agotado"', 'id="otro"')
    with pytest.raises(FetchError, match="Sin Stock"):
        bl.parse(raw, bl.normalize(AGOTADO))


def test_sin_opciones_pero_json_ld_con_precio_es_error_de_lectura():
    # Aunque aparezca la marca de agotado: si las opciones dejan de leerse pero el JSON-LD
    # sigue con precio, no es un agotado.
    raw = replaced("descuento_y_usado.html", 'class="opcionPrecio', 'class="otraCosa')
    raw += '<button id="noti-agotado"></button>'
    with pytest.raises(FetchError, match="JSON-LD tiene precio"):
        bl.parse(raw, bl.normalize(HAIL_MARY))


def test_precio_en_cero_es_error_de_lectura():
    raw = replaced(
        "audiolibro_sin_descuento.html",
        "&quot;precio_moneda_raw&quot;: &quot;24900.00&quot;",
        "&quot;precio_moneda_raw&quot;: &quot;0.00&quot;",
    )
    with pytest.raises(FetchError, match="sin precio"):
        bl.parse(raw, bl.normalize(AUDIOLIBRO))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("&quot;usado&quot;: &quot;0&quot;", "&quot;usado&quot;: &quot;no&quot;"),
        ("&quot;usado&quot;: &quot;0&quot;", "&quot;usado&quot;: null"),
        ("&quot;importacion&quot;: 0", "&quot;importacion&quot;: &quot;&quot;"),
        ("&quot;importacion&quot;: 0", "&quot;importacion&quot;: false"),
    ],
)
def test_usado_o_importacion_inesperado_es_error_de_lectura(old, new):
    raw = replaced("descuento_y_usado.html", old, new)
    with pytest.raises(FetchError, match="inesperado"):
        bl.parse(raw, bl.normalize(HAIL_MARY))


def test_variantes_usan_la_url_del_json_ld():
    # Con un slug y un ISBN pegados mal, la tienda redirige; las opciones salen con la URL buena.
    raw = fixture_text("buscalibre", "descuento_y_usado.html")
    ref = bl.normalize("https://www.buscalibre.cl/libro-x/1/p/62884122")
    assert [v.url for v in bl.parse_variants(raw, ref)] == [HAIL_MARY, HAIL_MARY + "?modo=todos"]


def test_otro_producto_es_error():
    url = HAIL_MARY.replace("62884122", "62884123")
    with pytest.raises(FetchError, match="otro producto"):
        parse("descuento_y_usado.html", url)


def test_categoria_no_es_producto():
    with pytest.raises(NotFoundError):
        parse("categoria_ficcion.html", HAIL_MARY)


@pytest.mark.parametrize(
    ("url", "external_id", "canonical", "mode"),
    [
        (HAIL_MARY, "62884122", HAIL_MARY, ""),
        (
            "http://buscalibre.cl/libro-proyecto-hail-mary/9789566190448/p/62884122/?utm_source=x",
            "62884122",
            HAIL_MARY,
            "",
        ),
        (HAIL_MARY + "?modo=TODOS", "62884122", HAIL_MARY + "?modo=todos", "todos"),
        (HAIL_MARY + "?modo=raro", "62884122", HAIL_MARY, ""),
        (AUDIOLIBRO + "#reviews", "63595406", AUDIOLIBRO, ""),
    ],
)
def test_normaliza(url, external_id, canonical, mode):
    ref = bl.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (external_id, canonical, mode)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.buscalibre.cl/",
        "https://www.buscalibre.cl/libros/ficcion",
        "https://www.buscalibre.cl/libros/search/?q=hail+mary",
        "https://www.buscalibre.cl/libros-envio-express-chile_t.html",
        "https://www.buscalibre.cl/ip/62884122",
        "https://www.buscalibre.cl/libro-proyecto-hail-mary/9789566190448/p/",
        "https://www.buscalibre.cl.evil.com/libro-proyecto-hail-mary/9789566190448/p/62884122",
        "https://evilbuscalibre.cl/libro-proyecto-hail-mary/9789566190448/p/62884122",
        "https://www.buscalibre.com/libro-proyecto-hail-mary/9789566190448/p/62884122",
        "https://www.buscalibre.com.ar/libro-proyecto-hail-mary/9789566190448/p/62884122",
        "https://www.buscalibre.com.mx/libro-proyecto-hail-mary/9789566190448/p/62884122",
        "https://www.buscalibre.pe/libro-proyecto-hail-mary/9789566190448/p/62884122",
    ],
)
def test_no_matchea(url):
    assert not bl.matches(url)
    assert find_processor(url) is None or find_processor(url).name != "buscalibre"
