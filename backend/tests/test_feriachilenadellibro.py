import asyncio
import json

import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors import woocommerce as woo_mod
from tracker.processors.feriachilenadellibro import FeriaChilenaDelLibroProcessor

feria = FeriaChilenaDelLibroProcessor()
BASE = "https://feriachilenadellibro.cl/producto"
SIN_RESPETO = f"{BASE}/9789566518068-sin-respeto/"
EXTRANJERO = f"{BASE}/9786313004485-el-extranjero/"
CORRESPONSAL = f"{BASE}/9786313005598-la-corresponsal/"
PECADOS = f"{BASE}/9789566419488-pecados-6-rey-de-la-gula/"


def parse(fixture, url):
    return feria.parse(fixture_text("feriachilenadellibro", fixture), feria.normalize(url))


def test_en_stock():
    r = parse("en_stock_sin_respeto.json", SIN_RESPETO)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "SIN RESPETO",
        19900,
        None,
        "CLP",
        True,
    )
    assert r.image_url.startswith("https://feriachilenadellibro.cl/wp-content/uploads/")


def test_agotado_con_precio():
    r = parse("agotado_el_extranjero.json", EXTRANJERO)
    assert (r.title, r.price, r.list_price, r.available) == ("EL EXTRANJERO", 8000, None, False)


def test_descuento_trae_precio_antes():
    r = parse("descuento_la_corresponsal.json", CORRESPONSAL)
    assert (r.title, r.price, r.list_price, r.available) == (
        "LA CORRESPONSAL",
        13760,
        17200,
        True,
    )


def test_preventa_se_lee_como_un_libro_con_stock():
    raw = fixture_text("feriachilenadellibro", "preventa_pecados_6.json")
    tags = [t["slug"] for t in json.loads(raw)["products"][0]["tags"]]
    assert "pre-venta" in tags
    r = parse("preventa_pecados_6.json", PECADOS)
    assert (r.title, r.price, r.list_price, r.available) == (
        "PECADOS 6. REY DE LA GULA",
        26100,
        None,
        True,
    )


def test_no_ofrece_variantes():
    raw = fixture_text("feriachilenadellibro", "en_stock_sin_respeto.json")
    assert feria.parse_variants(raw, feria.normalize(SIN_RESPETO)) == []
    # Sin selector, la query de variantes se ignora.
    assert feria.normalize(f"{SIN_RESPETO}?attribute_pa_encuadernacion=rustico").variant_id == ""


def test_no_existe():
    raw = json.dumps({"products": [], "variations": []})
    with pytest.raises(NotFoundError):
        feria.parse(raw, feria.normalize(f"{BASE}/9780000000000-no-existe/"))


API = "https://feriachilenadellibro.cl/wp-json/wc/store/v1/products"
ALL_STATUSES = "instock,outofstock,onbackorder"


def _fake_api(monkeypatch, responses):
    """Responde en orden las listas de `responses` y registra los `params` de cada llamada."""
    calls = []

    async def fake_get_text(url, *, params=None, **kw):
        assert url == API
        calls.append(params)
        return json.dumps(responses[len(calls) - 1])

    monkeypatch.setattr(woo_mod, "get_text", fake_get_text)
    return calls


def test_fetch_raw_con_stock_no_usa_el_filtro(monkeypatch):
    # El filtro `stock_status` usa una tabla de búsqueda que puede faltar para productos
    # que existen: solo se pide si la primera respuesta viene vacía.
    product = json.loads(fixture_text("feriachilenadellibro", "en_stock_sin_respeto.json"))
    calls = _fake_api(monkeypatch, [product["products"]])
    raw = asyncio.run(feria.fetch_raw(feria.normalize(SIN_RESPETO)))
    assert json.loads(raw) == product
    assert calls == [{"slug": "9789566518068-sin-respeto"}]


def test_fetch_raw_reintenta_con_stock_status_si_viene_vacia(monkeypatch):
    # La tienda oculta los agotados del catálogo: sin `stock_status`, `?slug=` da `[]`.
    product = json.loads(fixture_text("feriachilenadellibro", "agotado_el_extranjero.json"))
    calls = _fake_api(monkeypatch, [[], product["products"]])
    raw = asyncio.run(feria.fetch_raw(feria.normalize(EXTRANJERO)))
    assert json.loads(raw) == product
    assert feria.parse(raw, feria.normalize(EXTRANJERO)).available is False
    slug = "9786313004485-el-extranjero"
    assert calls == [{"slug": slug}, {"slug": slug, "stock_status": ALL_STATUSES}]


def test_fetch_raw_vacia_dos_veces_no_existe(monkeypatch):
    calls = _fake_api(monkeypatch, [[], []])
    ref = feria.normalize(f"{BASE}/9780000000000-no-existe/")
    raw = asyncio.run(feria.fetch_raw(ref))
    assert len(calls) == 2
    with pytest.raises(NotFoundError):
        feria.parse(raw, ref)


def test_en_oferta_sin_rebaja_no_trae_precio_antes():
    # `on_sale: true` con `price == regular_price` existe en la tienda: no es un descuento.
    data = json.loads(fixture_text("feriachilenadellibro", "descuento_la_corresponsal.json"))
    item = data["products"][0]
    item["on_sale"] = True
    item["prices"].update(price="17200", regular_price="17200", sale_price="17200")
    r = feria.parse(json.dumps(data), feria.normalize(CORRESPONSAL))
    assert (r.price, r.list_price, r.available) == (17200, None, True)


@pytest.mark.parametrize(
    "url",
    [
        SIN_RESPETO,
        f"{BASE}/9789566518068-sin-respeto",
        "https://www.feriachilenadellibro.cl/producto/9789566518068-sin-respeto/",
        "http://feriachilenadellibro.cl/producto/9789566518068-Sin-Respeto/?utm_source=x#a",
    ],
)
def test_normaliza_url(url):
    ref = feria.normalize(url)
    assert (ref.external_id, ref.canonical_url, ref.variant_id) == (
        "9789566518068-sin-respeto",
        SIN_RESPETO,
        "",
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert feria.domain() == "feriachilenadellibro.cl"
    assert find_processor(SIN_RESPETO).name == "feriachilenadellibro"
    assert not feria.matches("https://feriachilenadellibro.cl/")
    assert not feria.matches("https://feriachilenadellibro.cl/preventas/")
    assert not feria.matches("https://feriachilenadellibro.cl/categoria-producto/literatura/")
    assert not feria.matches("https://feriachilenadellibro.cl/etiqueta-producto/pre-venta/")
    assert not feria.matches("https://feriachilenadellibro.cl/producto/")
    assert not feria.matches("https://feriachilenadellibro.cl/?s=camus&post_type=product")
    assert not feria.matches("https://feriachilenadellibro.cl/producto/sin-respeto/otra-cosa/")
    assert not feria.matches("https://feriachilenadellibro.cl.evil.com/producto/sin-respeto/")
    assert not feria.matches("https://evilferiachilenadellibro.cl/producto/sin-respeto/")
    assert not feria.matches("https://wwwferiachilenadellibro.cl/producto/sin-respeto/")
