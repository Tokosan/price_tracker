import asyncio
import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors import ligafarmacia as liga_mod
from tracker.processors.ligafarmacia import LigaFarmaciaProcessor

liga = LigaFarmaciaProcessor()
NEUROVAL = "https://ligafarmacia.cl/product/007640030-neuroval-cd-10-mg"


def parse(fixture, kinf2):
    return liga.parse(
        fixture_text("ligafarmacia", fixture),
        liga.normalize(f"https://ligafarmacia.cl/product/{kinf2}"),
    )


def neuroval(**changes):
    """Fixture de Neuroval con cambios en el producto, lista para parsear."""
    body = json.loads(fixture_text("ligafarmacia", "neuroval_en_stock.json"))
    for key, value in changes.items():
        if value is ...:
            body["producto"].pop(key)
        else:
            body["producto"][key] = value
    return json.dumps(body)


def test_en_stock():
    r = parse("neuroval_en_stock.json", "007640030")
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Neuroval Cd 10 Mg (30 Compr. Dispersable)",
        11850,
        None,
        "CLP",
        True,
    )
    assert r.image_url == "https://ligafarmacia.cl/assets/fotos-productos/00764-1.webp"


def test_descuento_y_solo_venta_presencial():
    # La ficha muestra $36.235 y $42.630 tachado, con "Sólo venta presencial" (sin botón).
    body = json.loads(fixture_text("ligafarmacia", "neurok_descuento_solo_presencial.json"))
    assert (body["producto"]["comercio_elec"], body["producto"]["stock"]) == (False, 86)
    r = parse("neurok_descuento_solo_presencial.json", "017580030")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Neurok 20 Mg (30 Cápsulas)",
        36235,
        42630,
        False,
    )


def test_sin_stock_conserva_el_precio():
    r = parse("valproico_sin_stock.json", "007790120")
    assert (r.title, r.price, r.list_price, r.available) == (
        "Ac. Valproico 250 Mg (120 Comprimidos)",
        18960,
        None,
        False,
    )


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json", "999999999")


def test_sin_precio_con_descuento_usa_el_precio():
    r = liga.parse(neuroval(precio_con_dscto=...), liga.normalize(NEUROVAL))
    assert (r.price, r.list_price) == (11850, None)


def test_sin_contenido_el_titulo_es_el_nombre():
    r = liga.parse(neuroval(contenido=""), liga.normalize(NEUROVAL))
    assert r.title == "Neuroval Cd 10 Mg"


def test_precio_como_string_numerico():
    r = liga.parse(neuroval(precio="11850", precio_con_dscto="9990"), liga.normalize(NEUROVAL))
    assert (r.price, r.list_price) == (9990, 11850)


@pytest.mark.parametrize(
    "changes",
    [
        {"precio": 0},
        {"precio": -100},
        {"precio": "11.850"},
        {"precio": 11850.5},
        {"precio": None},
        {"precio": True},
        {"precio": ...},
        {"precio_con_dscto": 0},
        {"precio_con_dscto": "gratis"},
    ],
)
def test_precio_roto_es_error_de_lectura(changes):
    with pytest.raises(FetchError):
        liga.parse(neuroval(**changes), liga.normalize(NEUROVAL))


@pytest.mark.parametrize(
    "changes",
    [
        {"stock": ...},
        {"stock": "106"},
        {"stock": None},
        {"comercio_elec": ...},
        {"comercio_elec": "true"},
        {"nombre_medicamento": ""},
        {"kinf2": "017580030"},
    ],
)
def test_datos_faltantes_son_error_de_lectura(changes):
    # Nunca un agotado: un cambio en el catálogo no debe disparar OUT_OF_STOCK.
    with pytest.raises(FetchError) as exc:
        liga.parse(neuroval(**changes), liga.normalize(NEUROVAL))
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize("raw", ["<html>error</html>", "[]", "{}", '{"producto": []}', "null"])
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError) as exc:
        liga.parse(raw, liga.normalize(NEUROVAL))
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize(
    ("path", "url"),
    [
        (
            "/assets/fotos-productos/00764-1.webp",
            "https://ligafarmacia.cl/assets/fotos-productos/00764-1.webp",
        ),
        # Las .jpg del documento responden el HTML de la SPA; la foto real es .webp.
        (
            "/assets/fotos-productos/00130-1.jpg",
            "https://ligafarmacia.cl/assets/fotos-productos/00130-1.webp",
        ),
        (
            "https://firebasestorage.googleapis.com/v0/b/x/o/foto.JPG?alt=media",
            "https://firebasestorage.googleapis.com/v0/b/x/o/foto.JPG?alt=media",
        ),
        (None, None),
        ("", None),
        ("javascript:alert(1)", None),
    ],
)
def test_imagen(path, url):
    body = json.loads(neuroval())
    body["imagen"] = path
    assert liga.parse(json.dumps(body), liga.normalize(NEUROVAL)).image_url == url


# Documentos de Firestore mínimos, con la forma de la API REST.
def _doc(field, items):
    return json.dumps({"fields": {field: {"arrayValue": {"values": items}}}})


def _map(**fields):
    return {"mapValue": {"fields": fields}}


CATALOG = _doc(
    "sku",
    [
        _map(
            kinf2={"stringValue": "007640030"},
            nombre_medicamento={"stringValue": "NEUROVAL CD 10 MG"},
            contenido={"stringValue": "30 Compr. Dispersable"},
            precio={"integerValue": "11850"},
            precio_con_dscto={"integerValue": "11850"},
            stock={"integerValue": "106"},
            comercio_elec={"booleanValue": True},
            imagenes={"arrayValue": {}},
            pap=_map(requerido={"integerValue": "0"}),
            otro={"nullValue": None},
        ),
        _map(kinf2={"stringValue": "007790120"}, stock={"integerValue": "0"}),
    ],
)
IMAGES = _doc(
    "images_med",
    [
        _map(
            kinf2={"stringValue": "007640030"},
            kinf={"stringValue": "00764"},
            image={
                "arrayValue": {
                    "values": [
                        {"stringValue": "/assets/fotos-productos/00764-1.webp"},
                        {"stringValue": "/assets/fotos-productos/00764-2.webp"},
                    ]
                }
            },
        ),
    ],
)


@pytest.fixture
def firestore(monkeypatch):
    """Firestore falso: cuenta las descargas y deja la caché vacía antes y después."""
    calls = []
    docs = {liga_mod.CATALOG_URL: CATALOG, liga_mod.IMAGES_URL: IMAGES}

    async def fake_get_text(url, **kwargs):
        calls.append(url)
        return docs[url]

    monkeypatch.setattr(liga_mod, "get_text", fake_get_text)
    monkeypatch.setattr(liga_mod, "_cache", None)
    # Cada test corre su propio event loop: un lock nuevo para no quedar atado a otro.
    monkeypatch.setattr(liga_mod, "_cache_lock", asyncio.Lock())
    yield docs, calls


def test_fetch_raw_arma_el_json_chico(firestore):
    _, calls = firestore
    raw = asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))
    assert calls == [liga_mod.CATALOG_URL, liga_mod.IMAGES_URL]
    body = json.loads(raw)
    assert body["imagen"] == "/assets/fotos-productos/00764-1.webp"
    assert body["producto"]["precio"] == 11850 and body["producto"]["stock"] == 106
    assert body["producto"]["comercio_elec"] is True
    assert body["producto"]["pap"] == {"requerido": 0}
    assert body["producto"]["otro"] is None
    r = liga.parse(raw, liga.normalize(NEUROVAL))
    assert (r.price, r.available) == (11850, True)


def test_fetch_raw_producto_inexistente(firestore):
    raw = asyncio.run(liga.fetch_raw(liga.normalize("https://ligafarmacia.cl/product/999999999")))
    assert json.loads(raw) == {"producto": None, "imagen": None}
    # Sin foto: imagen null.
    raw = asyncio.run(liga.fetch_raw(liga.normalize("https://ligafarmacia.cl/product/007790120")))
    assert json.loads(raw)["imagen"] is None


def test_una_sola_descarga_para_varios_productos(firestore):
    _, calls = firestore

    async def tick():
        urls = [NEUROVAL, "https://ligafarmacia.cl/product/007790120", NEUROVAL]
        return await asyncio.gather(*(liga.fetch_raw(liga.normalize(u)) for u in urls))

    asyncio.run(tick())
    asyncio.run(tick())
    assert len(calls) == 2


def test_la_cache_vence(firestore, monkeypatch):
    _, calls = firestore
    now = [1000.0]
    monkeypatch.setattr(liga_mod.time, "monotonic", lambda: now[0])
    asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))
    now[0] += liga_mod.CACHE_TTL - 1
    asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))
    assert len(calls) == 2
    now[0] += 2
    asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))
    assert len(calls) == 4


@pytest.mark.parametrize(
    "catalog",
    [
        "<html></html>",
        "{}",
        '{"fields": {}}',
        '{"fields": {"sku": {"arrayValue": {}}}}',
        '{"fields": {"sku": "x"}}',
        '{"fields": {"otra": {"arrayValue": {"values": [1]}}}}',
        '{"fields": {"sku": {"arrayValue": {"values": [{"stringValue": "x"}]}}}}',
    ],
)
def test_documento_con_otra_forma_es_error_de_lectura(firestore, catalog):
    docs, _ = firestore
    docs[liga_mod.CATALOG_URL] = catalog
    with pytest.raises(FetchError) as exc:
        asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))
    assert not isinstance(exc.value, NotFoundError)
    # Una descarga fallida no queda en la caché.
    assert liga_mod._cache is None


def test_fotos_con_otra_forma_es_error_de_lectura(firestore):
    docs, _ = firestore
    docs[liga_mod.IMAGES_URL] = "{}"
    with pytest.raises(FetchError):
        asyncio.run(liga.fetch_raw(liga.normalize(NEUROVAL)))


def test_titulo_como_la_ficha():
    assert liga_mod._title_case("AC. VALPROICO 250 MG (120 Comprimidos)") == (
        "Ac. Valproico 250 Mg (120 Comprimidos)"
    )


def test_sin_variantes():
    assert liga.supports_variants is False
    assert liga.parse_variants("{}", liga.normalize(NEUROVAL)) == []


@pytest.mark.parametrize(
    "u",
    [
        NEUROVAL,
        "https://ligafarmacia.cl/product/007640030",
        "https://www.ligafarmacia.cl/product/007640030-neuroval-cd-10-mg",
        "http://ligafarmacia.cl/product/007640030-neuroval-cd-10-mg/",
        "https://LIGAFARMACIA.CL/product/007640030-Neuroval-CD-10-MG?utm_source=x#top",
        "https://ligafarmacia.cl/product/007640030-otro-nombre",
    ],
)
def test_normaliza_url(u):
    assert liga.normalize(u) == ProductRef("007640030", "https://ligafarmacia.cl/product/007640030")


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(NEUROVAL).name == "ligafarmacia"
    for u in [
        "https://ligafarmacia.cl/",
        "https://ligafarmacia.cl/product/",
        "https://ligafarmacia.cl/product/neuroval-cd-10-mg",
        "https://ligafarmacia.cl/product/00764",
        "https://ligafarmacia.cl/product/0076400301",
        "https://ligafarmacia.cl/product/007640030-neuroval/extra",
        "https://ligafarmacia.cl/medicamentos/salud-mental",
        "https://ligafarmacia.cl/medicamentos/salud-mental/clotiazepam",
        "https://ligafarmacia.cl/medicamentos?busqueda=neuroval",
        "https://ligafarmacia.cl/carrito",
        "https://ligafarmacia.cl/blog/epilepsia",
        "https://ligafarmacia.cl.evil.com/product/007640030",
        "https://evilligafarmacia.cl/product/007640030",
        "https://shop.ligafarmacia.cl/product/007640030",
        "ftp://ligafarmacia.cl/product/007640030",
        "javascript://ligafarmacia.cl/product/007640030",
    ]:
        assert not liga.matches(u), u
