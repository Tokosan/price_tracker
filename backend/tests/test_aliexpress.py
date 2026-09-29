from urllib.parse import parse_qsl

import httpx
import pytest

from tests.conftest import fixture_text
from tracker.config import settings
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors import aliexpress as ae_mod
from tracker.processors.aliexpress import AliExpressProcessor, sign

ae = AliExpressProcessor()
ITEM = "https://www.aliexpress.com/item/1005006153442431.html"


def parse(fixture: str, url: str = ITEM):
    return ae.parse(fixture_text("aliexpress", fixture), ae.normalize(url))


def test_con_descuento():
    r = parse("con_descuento.json")
    assert r.title == "Teclado mecánico inalámbrico 75%"
    assert r.price == 2499
    assert r.list_price == 4998
    assert r.currency == "USD"
    assert r.available is True
    assert r.image_url.startswith("https://ae-pic-a1.aliexpress-media.com/")


def test_sin_descuento_no_informa_precio_antes():
    r = parse("sin_descuento.json", "https://www.aliexpress.com/item/1005001234567890.html")
    assert r.price == 310
    assert r.list_price is None


def test_otro_producto_en_la_respuesta_es_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("sin_descuento.json")


def test_no_encontrado():
    with pytest.raises(NotFoundError, match="programa de afiliados"):
        parse("no_encontrado.json")


def test_error_de_la_api_cuenta_como_fallo():
    with pytest.raises(FetchError, match="IncompleteSignature"):
        parse("firma_invalida.json")


@pytest.mark.parametrize(
    "url",
    [
        ITEM,
        "https://es.aliexpress.com/item/1005006153442431.html?spm=a2g0o.home&gatewayAdapt=glo2esp",
        "https://aliexpress.us/item/1005006153442431.html",
        "https://m.aliexpress.com/item/1005006153442431.html#reviews",
        "https://www.aliexpress.com/i/1005006153442431.html",
    ],
)
def test_normaliza_url(url):
    assert ae.matches(url)
    assert find_processor(url).name == "aliexpress"
    ref = ae.normalize(url)
    assert ref.external_id == "1005006153442431"
    assert ref.canonical_url == ITEM


def test_no_matchea_otras_paginas_ni_dominios():
    assert not ae.matches("https://www.aliexpress.com/")
    assert not ae.matches("https://www.aliexpress.com/store/1101234567")
    assert not ae.matches("https://aliexpress.com.evil.com/item/1005006153442431.html")
    assert not ae.matches("https://evil.com/aliexpress.com/item/1005006153442431.html")


def test_link_corto_matchea_pero_hay_que_expandirlo():
    assert ae.matches("https://a.aliexpress.com/_mKqZ1a2")
    assert not ae.matches("https://a.aliexpress.com/")
    with pytest.raises(ValueError):
        ae.normalize("https://a.aliexpress.com/_mKqZ1a2")


def test_firma():
    # MD5("secret" + "akeya" + "methodm" + "secret"), claves ordenadas, en mayúsculas.
    assert sign("secret", {"method": "m", "akey": "a"}) == "C44F58FDB9693D0881A3D375305B68E7"


async def test_expande_link_corto(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "a.aliexpress.com":
            target = "https%3A%2F%2Fes.aliexpress.com%2Fitem%2F1005006153442431.html%3Fsrc%3Dapp"
            return httpx.Response(
                302,
                headers={
                    "location": f"https://star.aliexpress.com/share/share.htm?redirectUrl={target}"
                },
            )
        raise AssertionError(f"no debería pedir {request.url}")

    monkeypatch.setattr(ae_mod, "_transport", httpx.MockTransport(handler))
    assert await ae.expand("https://a.aliexpress.com/_mKqZ1a2") == ITEM
    assert seen == ["https://a.aliexpress.com/_mKqZ1a2"]  # no se pide la página final


async def test_link_corto_no_sigue_redirects_fuera_de_aliexpress(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/admin"})

    monkeypatch.setattr(ae_mod, "_transport", httpx.MockTransport(handler))
    with pytest.raises(NotFoundError):
        await ae.expand("https://a.aliexpress.com/_mKqZ1a2")
    assert seen == ["a.aliexpress.com"]


async def test_url_normal_no_se_expande():
    assert await ae.expand(ITEM) == ITEM


async def test_sin_credenciales_no_llama_a_la_api(monkeypatch):
    monkeypatch.setattr(settings, "aliexpress_app_key", "")
    with pytest.raises(FetchError, match="no está configurado"):
        await ae.fetch_raw(ae.normalize(ITEM))


async def test_fetch_firma_la_peticion(monkeypatch):
    monkeypatch.setattr(settings, "aliexpress_app_key", "123456")
    monkeypatch.setattr(settings, "aliexpress_app_secret", "s3cr3t")
    monkeypatch.setattr(settings, "aliexpress_tracking_id", "")
    monkeypatch.setattr(settings, "aliexpress_currency", "USD")
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(parse_qsl(request.content.decode()))
        return httpx.Response(200, text=fixture_text("aliexpress", "con_descuento.json"))

    monkeypatch.setattr(ae_mod, "_transport", httpx.MockTransport(handler))
    r = await ae.fetch(ae.normalize(ITEM))
    assert r.price == 2499
    assert sent["method"] == "aliexpress.affiliate.productdetail.get"
    assert sent["product_ids"] == "1005006153442431"
    assert sent["target_currency"] == "USD"
    assert sent["country"] == "CL"
    assert "tracking_id" not in sent
    signature = sent.pop("sign")
    assert signature == sign("s3cr3t", sent)


async def test_fetch_http_error(monkeypatch):
    monkeypatch.setattr(settings, "aliexpress_app_key", "123456")
    monkeypatch.setattr(settings, "aliexpress_app_secret", "s3cr3t")
    monkeypatch.setattr(
        ae_mod, "_transport", httpx.MockTransport(lambda r: httpx.Response(503, text="{}"))
    )
    with pytest.raises(FetchError, match="HTTP 503"):
        await ae.fetch_raw(ae.normalize(ITEM))
