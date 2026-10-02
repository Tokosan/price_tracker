import pytest

from tests.conftest import fixture_text
from tracker.processors import PROCESSORS, FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.pcfactory import PcFactoryProcessor

pcf = PcFactoryProcessor()


def ref(product_id: str) -> ProductRef:
    return ProductRef(product_id, f"https://www.pcfactory.cl/producto/{product_id}")


def test_esta_registrado():
    assert PROCESSORS["pcfactory"].label == "PC Factory"
    assert find_processor("https://www.pcfactory.cl/producto/1579").name == "pcfactory"


def test_en_stock_sin_descuento():
    # 51000: stock "1" y referencia null. La ficha muestra $303.990 por transferencia.
    r = pcf.parse(fixture_text("pcfactory", "en_stock.json"), ref("51000"))
    assert r.title == "Audífonos Headset Sennheiser MOMENTUM 4 Bluetooth Negro"
    assert r.price == 303990  # efectivo, no normal (319.990) ni debito (307.190)
    assert r.list_price is None
    assert r.currency == "CLP"
    assert r.available is True
    assert r.image_url == "https://assets.pcfactory.cl/public/foto/51000/1_500.jpg"


def test_descuento():
    r = pcf.parse(fixture_text("pcfactory", "descuento.json"), ref("1579"))
    assert r.title == "Cable USB 2.0 A/A 4.5m Extensión"
    assert r.price == 1990
    assert r.list_price == 4990
    assert r.available is True  # stock "+100"


def test_descuento_con_stock_mas_50():
    r = pcf.parse(fixture_text("pcfactory", "descuento_toner.json"), ref("1205"))
    assert r.title == "Toner Original HP 12A LaserJet Negro"
    assert r.price == 134990
    assert r.list_price == 199990
    assert r.available is True  # stock "+50"


def test_agotado_conserva_el_precio():
    r = pcf.parse(fixture_text("pcfactory", "agotado.json"), ref("46241"))
    assert r.title == "Audifonos In-ear Bluetooth JBL Tune 125BT Negro"
    assert r.available is False  # stock "0"
    assert r.price == 41390
    assert r.list_price is None


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        pcf.parse(fixture_text("pcfactory", "no_encontrado.json"), ref("99999999"))


def _raw(stock="+50", efectivo="1990.0000", referencia="null", product_id=1):
    return (
        f'{{"producto": {{"id": {product_id}, "nombre": "X", "stock": {{"aproximado": "{stock}"}}}},'
        f' "precio": {{"id": {product_id}, "precio": {{"efectivo": {efectivo},'
        f' "referencia": {referencia}}}}}}}'
    )


@pytest.mark.parametrize("referencia", ["null", "0.0000", "1990.0000", "990.0000"])
def test_referencia_no_mayor_no_es_list_price(referencia):
    r = pcf.parse(_raw(referencia=referencia), ref("1"))
    assert r.price == 1990
    assert r.list_price is None


def test_precio_en_cero_o_ausente_queda_sin_precio():
    assert pcf.parse(_raw(efectivo="0.0000"), ref("1")).price is None
    assert pcf.parse(_raw(efectivo="null"), ref("1")).price is None
    assert pcf.parse(_raw(efectivo="null", referencia="4990"), ref("1")).list_price is None


@pytest.mark.parametrize("stock,available", [("1", True), ("+100", True), ("0", False)])
def test_stock(stock, available):
    assert pcf.parse(_raw(stock=stock), ref("1")).available is available


@pytest.mark.parametrize(
    "producto",
    [
        '{"id": 1, "nombre": "X", "precio": 1}',
        '{"id": 1, "nombre": "X", "stock": null}',
        '{"id": 1, "nombre": "X", "stock": {}}',
        '{"id": 1, "nombre": "X", "stock": {"aproximado": null}}',
        '{"id": 1, "nombre": "X", "stock": {"aproximado": ""}}',
    ],
)
def test_sin_stock_en_la_respuesta_es_fetch_error_y_no_agotado(producto):
    raw = f'{{"producto": {producto}, "precio": {{"precio": {{"efectivo": 1990}}}}}}'
    with pytest.raises(FetchError):
        pcf.parse(raw, ref("1"))


def test_otro_error_de_la_api_es_fetch_error_y_no_not_found():
    raw = '{"producto": {"errors": [{"code": "500"}]}, "precio": {}}'
    with pytest.raises(FetchError) as exc:
        pcf.parse(raw, ref("1"))
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize("raw", ["<html>mantención</html>", "[]", '{"producto": {}}'])
def test_respuesta_rota_es_fetch_error(raw):
    with pytest.raises(FetchError):
        pcf.parse(raw, ref("1"))


def test_producto_distinto_es_fetch_error():
    with pytest.raises(FetchError):
        pcf.parse(_raw(product_id=2), ref("1"))


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pcfactory.cl/producto/1579",
        "https://www.pcfactory.cl/producto/1579-spektra-cable-usb-2-0-a-a-4-5m-extension",
        "https://pcfactory.cl/producto/1579/",
        "http://www.pcfactory.cl/producto/1579?utm_source=x#specs",
        "HTTPS://WWW.PCFACTORY.CL/producto/1579-Spektra-Cable",
        "  https://www.pcfactory.cl/producto/1579  ",
    ],
)
def test_normaliza_url(url):
    assert pcf.matches(url)
    r = pcf.normalize(url)
    assert r.external_id == "1579"
    assert r.canonical_url == "https://www.pcfactory.cl/producto/1579"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pcfactory.cl.evil.com/producto/1579",
        "https://evilpcfactory.cl/producto/1579",
        "https://www.pcfactory.cl/",
        "https://www.pcfactory.cl/producto/",
        "https://www.pcfactory.cl/producto/abc",
        "https://www.pcfactory.cl/audifonos?categoria=884",
        "https://www.pcfactory.cl/busqueda?q=1579",
        "https://www.pcfactory.cl/producto/1579/otra",
        "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos/1579",
    ],
)
def test_no_matchea(url):
    assert not pcf.matches(url)
    with pytest.raises(ValueError):
        pcf.normalize(url)


async def test_fetch_raw_junta_producto_y_precio(monkeypatch):
    urls = []

    async def fake_get_text(url, **kwargs):
        urls.append(url)
        if url.endswith("/precio"):
            return '{"id": 1579, "precio": {"efectivo": 1990.0000, "referencia": 4990.0000}}'
        return '{"id": 1579, "nombre": "Cable", "stock": {"aproximado": "+100"}}'

    monkeypatch.setattr("tracker.processors.pcfactory.get_text", fake_get_text)
    r = await pcf.fetch(ref("1579"))
    base = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos/1579"
    assert urls == [base, f"{base}/precio"]
    assert (r.price, r.list_price, r.available) == (1990, 4990, True)
