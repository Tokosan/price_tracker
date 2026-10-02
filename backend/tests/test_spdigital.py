import json

import pytest
from curl_cffi.requests.exceptions import RequestException

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor, http
from tracker.processors.spdigital import API_URL, CHANNEL, SpDigitalProcessor

sp = SpDigitalProcessor()
CLOUD = (
    "https://www.spdigital.cl/audifonos-gamer-hyperx-cloud-iii-s-wireless-over-ear-24ghz-"
    "bluetooth-pc-ps-moviles-blackred/"
)
RTX = "https://www.spdigital.cl/dual-rtx4060-o8g/"
M90 = "https://www.spdigital.cl/mouse-logitech-m90-al%C3%A1mbrico-usb-1000dpi-negro-para-macpc/"


def parse(fixture, url):
    return sp.parse(fixture_text("spdigital", fixture), sp.normalize(url))


def test_descuento_precio_por_transferencia():
    # p = 104.495 (otros medios); 104.495 · 149.990 / 156.740 = 99.995,6 → 99.990.
    r = parse("descuento_cloud_iii_s.json", CLOUD)
    assert r.title.startswith("Audifonos Gamer HyperX Cloud III S Wireless")
    assert (r.price, r.list_price, r.currency, r.available) == (99990, 149990, "CLP", True)
    assert r.image_url.startswith("https://media.spdigital.cl/thumbnails/")


def test_agotado_sin_oferta():
    # Sin oferta, p = other y la transferencia es justo `cash`: no hay precio tachado.
    r = parse("agotado_rtx4060.json", RTX)
    assert (r.price, r.list_price, r.available) == (499990, None, False)


def test_slug_con_tilde():
    r = parse("slug_con_tilde_mouse_m90.json", M90)
    assert r.title == "Mouse Logitech M90, Alámbrico, USB, 1000DPI, Negro - para Mac/PC"
    assert (r.price, r.list_price, r.available) == (5990, 9990, True)


def test_no_existe():
    with pytest.raises(NotFoundError):
        parse("no_existe.json", RTX)


def _edit(fixture, **fields):
    body = json.loads(fixture_text("spdigital", fixture))
    body["data"]["product"].update(fields)
    return json.dumps(body)


@pytest.mark.parametrize(
    "meta",
    [
        None,
        "",
        "no es json",
        '{"otro-canal": {"cash": 1, "other": 2}}',
        '{"sp-digital": {"cash": 149990}}',
        '{"sp-digital": {"cash": 149990, "other": 0}}',
        '{"sp-digital": {"cash": "x", "other": 156740}}',
        "[1, 2]",
    ],
)
def test_sin_metadato_de_precio_no_inventa_precio(meta):
    r = sp.parse(_edit("descuento_cloud_iii_s.json", pricingMeta=meta), sp.normalize(CLOUD))
    assert (r.price, r.list_price) == (None, None)
    assert r.available is True


def test_sin_pricing_no_inventa_precio():
    r = sp.parse(_edit("descuento_cloud_iii_s.json", pricing=None), sp.normalize(CLOUD))
    assert (r.price, r.list_price) == (None, None)


@pytest.mark.parametrize("variant", [None, {}, {"quantityAvailable": None}])
def test_sin_cantidad_es_agotado(variant):
    raw = _edit("descuento_cloud_iii_s.json", defaultVariant=variant)
    assert sp.parse(raw, sp.normalize(CLOUD)).available is False


@pytest.mark.parametrize(
    "raw",
    [
        "<html>Cloudflare</html>",
        '{"errors": [{"message": "Cannot query field"}]}',
        '{"data": null}',
        '{"data": {}}',
        "[]",
    ],
)
def test_respuesta_rara_es_error_de_lectura(raw):
    with pytest.raises(FetchError) as exc:
        sp.parse(raw, sp.normalize(RTX))
    assert not isinstance(exc.value, NotFoundError)


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        (RTX, "dual-rtx4060-o8g"),
        ("https://www.spdigital.cl/dual-rtx4060-o8g", "dual-rtx4060-o8g"),
        ("http://SPDIGITAL.CL/Dual-RTX4060-O8G/?utm_source=wa#specs", "dual-rtx4060-o8g"),
        (M90, "mouse-logitech-m90-alámbrico-usb-1000dpi-negro-para-macpc"),
        (
            "https://www.spdigital.cl/mouse-logitech-m90-alámbrico-usb-1000dpi-negro-para-macpc/",
            "mouse-logitech-m90-alámbrico-usb-1000dpi-negro-para-macpc",
        ),
    ],
)
def test_normaliza_url(url, slug):
    ref = sp.normalize(url)
    assert (ref.external_id, ref.variant_id) == (slug, "")
    assert sp.normalize(ref.canonical_url) == ref
    assert ref.canonical_url.startswith("https://www.spdigital.cl/") and ref.canonical_url.endswith(
        "/"
    )


def test_url_canonica_codifica_la_tilde():
    assert sp.normalize(M90).canonical_url == M90


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(RTX).name == "spdigital"
    assert find_processor(M90).name == "spdigital"
    assert not sp.matches("https://www.spdigital.cl/")
    assert not sp.matches("https://www.spdigital.cl/categories/tarjetas-de-video/")
    assert not sp.matches("https://www.spdigital.cl/search/?q=rtx")
    assert not sp.matches("https://www.spdigital.cl/landing/cyber/")
    assert not sp.matches("https://www.spdigital.cl/search/")
    assert not sp.matches("https://www.spdigital.cl/dual_rtx4060/")
    assert not sp.matches("https://www.spdigital.cl.evil.com/dual-rtx4060-o8g/")
    assert not sp.matches("https://evilspdigital.cl/dual-rtx4060-o8g/")
    assert not sp.matches("https://bff.spdigital.cl/api/v1/saleor")
    with pytest.raises(ValueError):
        sp.normalize("https://www.spdigital.cl/categories/notebooks/")


async def test_fetch_manda_la_query_del_slug(monkeypatch):
    calls = []

    async def fake(url, payload, **kw):
        calls.append((url, payload))
        return fixture_text("spdigital", "slug_con_tilde_mouse_m90.json")

    monkeypatch.setattr("tracker.processors.spdigital.post_json_impersonate", fake)
    r = await sp.fetch(sp.normalize(M90))
    assert r.price == 5990
    ((url, payload),) = calls
    assert url == API_URL
    assert payload["variables"] == {
        "slug": "mouse-logitech-m90-alámbrico-usb-1000dpi-negro-para-macpc",
        "channel": CHANNEL,
    }
    assert (
        "quantityAvailable" in payload["query"] and 'metafield(key: "pricing")' in payload["query"]
    )


class _FakeSession:
    def __init__(self, result, **kw):
        self.result, self.kw, self.posted = result, kw, None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kw):
        self.posted = (url, kw)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (_Resp(404), NotFoundError),
        (_Resp(403), FetchError),
        (_Resp(500), FetchError),
        (RequestException("timeout"), FetchError),
    ],
)
async def test_post_json_impersonate_errores(monkeypatch, result, error):
    monkeypatch.setattr(http, "AsyncSession", lambda **kw: _FakeSession(result, **kw))
    with pytest.raises(error):
        await http.post_json_impersonate(API_URL, {"query": "{}"})


async def test_post_json_impersonate_ok(monkeypatch):
    sessions = []

    def session(**kw):
        sessions.append(_FakeSession(_Resp(200, '{"data": {}}'), **kw))
        return sessions[-1]

    monkeypatch.setattr(http, "AsyncSession", session)
    text = await http.post_json_impersonate(API_URL, {"query": "{}"}, headers={"X-A": "1"})
    assert text == '{"data": {}}'
    s = sessions[0]
    assert s.kw["impersonate"] == "chrome" and s.kw["headers"]["X-A"] == "1"
    assert s.posted == (API_URL, {"json": {"query": "{}"}, "timeout": 30})
