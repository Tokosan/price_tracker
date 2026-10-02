import asyncio
import json

import httpx
import pytest

from tests.conftest import fixture_text
from tracker.processors import PROCESSORS, FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors import cruzverde as cvmod
from tracker.processors.cruzverde import CruzVerdeProcessor

cv = CruzVerdeProcessor()
URL = "https://www.cruzverde.cl/xumadol-paracetamol-1000-mg-20-comprimidos/266145.html"


def ref(product_id: str) -> ProductRef:
    return ProductRef(product_id, f"https://www.cruzverde.cl/x/{product_id}.html")


def test_esta_registrado():
    assert PROCESSORS["cruzverde"].label == "Cruz Verde"
    assert find_processor(URL).name == "cruzverde"


def test_descuento():
    # 266145: la ficha muestra $11.390 tachado y $7.690.
    r = cv.parse(fixture_text("cruzverde", "descuento.json"), ref("266145"))
    assert r.title == "Xumadol Paracetamol 1000 mg 20 Comprimidos"
    assert r.price == 7690
    assert r.list_price == 11390
    assert r.currency == "CLP"
    assert r.available is True
    assert r.image_url.startswith("https://beta.cruzverde.cl/")
    assert r.image_url.endswith("/266145-xumadol-comprimido-20-unidades-paracetamol-1000-mg.jpg")


def test_sin_descuento_no_trae_price_sale():
    # Sin oferta solo viene `price-list-cl`.
    r = cv.parse(fixture_text("cruzverde", "sin_descuento.json"), ref("124158"))
    assert r.title == "Edt Eau de Toilette de 25 mL"
    assert r.price == 10990
    assert r.list_price is None
    assert r.available is True


def test_agotado_conserva_el_precio():
    # stock 0: la ficha dice "Stock No Disponible" en despacho y retiro, y sigue el precio.
    r = cv.parse(fixture_text("cruzverde", "agotado.json"), ref("85454"))
    assert r.title == "Women Antitranspirante Powder Dry Barra 50 grs"
    assert r.available is False
    assert r.price == 4290
    assert r.list_price is None


def test_receta_descarta_la_promocion_por_dias_de_la_semana():
    # La ficha muestra $27.490, $24.741 y $17.868. El 24.741 lo pone FPW050 ("10%-planW"),
    # que rige solo algunos días de la semana: se usa el normal, sin precio "antes". El
    # 17.868 (-35 %, `healthNeedsPrice`, "necesidad de salud") tampoco se usa.
    raw = fixture_text("cruzverde", "receta.json")
    data = json.loads(raw)["productData"]
    assert data["appliedPromotions"]["price-sale-cl"]["promotionId"] == "FPW050"
    assert data["healthNeedsPrice"]["price"] == 17868
    r = cv.parse(raw, ref("293816"))
    assert r.price == 27490
    assert r.list_price is None
    assert r.available is True


def test_receta_retenida():
    # Receta retenida (`prescription: restricted`, solo retiro en tienda): igual tiene
    # precio. También con FPW050 aplicada: queda el normal.
    r = cv.parse(fixture_text("cruzverde", "receta_retenida.json"), ref("199479"))
    assert r.title == "Clonazepam 2 mg 30 Comprimidos"
    assert r.price == 5990
    assert r.list_price is None
    assert r.available is True


def _receta_con(promotions_edit):
    """Copia de receta.json con `promotions` modificado por `promotions_edit`."""
    body = json.loads(fixture_text("cruzverde", "receta.json"))
    promotions_edit(body["productData"]["promotions"])
    return json.dumps(body)


def test_promocion_solo_con_fechas_se_mantiene():
    def sin_recurrencia(promotions):
        for promo in promotions:
            info = promo["assignmentInformation"]
            info["schedule"] = {"startDate": "2026-09-01T04:00:00.000Z"}
            info["endDate"] = "2026-10-31T03:00:00.000Z"
            for a in info.get("activeCampaignAssignments") or []:
                a["schedule"] = {"endDate": "2026-10-31T03:00:00.000Z"}

    r = cv.parse(_receta_con(sin_recurrencia), ref("293816"))
    assert r.price == 24741
    assert r.list_price == 27490


def test_recurrencia_solo_en_la_campana_tambien_descarta():
    def solo_en_campana(promotions):
        for promo in promotions:
            promo["assignmentInformation"]["schedule"] = {}

    r = cv.parse(_receta_con(solo_en_campana), ref("293816"))
    assert (r.price, r.list_price) == (27490, None)


def test_promocion_aplicada_que_no_esta_en_promotions_se_descarta():
    # No se puede saber si es recurrente: se descarta por si acaso.
    r = cv.parse(_receta_con(lambda promotions: promotions.clear()), ref("293816"))
    assert (r.price, r.list_price) == (27490, None)


def test_rebajado_de_catalogo_se_mantiene():
    # descuento.json trae FPW050 en `promotions`, pero `appliedPromotions` viene vacío: el
    # rebajado es de catálogo, no de esa promoción.
    raw = fixture_text("cruzverde", "descuento.json")
    data = json.loads(raw)["productData"]
    assert data["appliedPromotions"] == {}
    assert any(p["id"] == "FPW050" for p in data["promotions"])
    r = cv.parse(raw, ref("266145"))
    assert (r.price, r.list_price) == (7690, 11390)


def _raw(prices, stock=10, product_id="1"):
    return json.dumps(
        {"productData": {"id": product_id, "name": " X ", "prices": prices, "stock": stock}}
    )


@pytest.mark.parametrize(
    "prices,price,list_price",
    [
        ({"price-sale-cl": 900, "price-list-cl": 1000}, 900, 1000),
        ({"price-sale-cl": 1000, "price-list-cl": 1000}, 1000, None),
        ({"price-sale-cl": 1100, "price-list-cl": 1000}, 1100, None),
        ({"price-list-cl": 1000}, 1000, None),
        ({"price-sale-cl": 0, "price-list-cl": 1000}, 1000, None),
        ({"price-sale-cl": 900}, 900, None),
        ({"price-list-cl": 0}, None, None),
        ({}, None, None),
        (None, None, None),
    ],
)
def test_criterio_de_precio(prices, price, list_price):
    r = cv.parse(_raw(prices), ref("1"))
    assert r.title == "X"
    assert (r.price, r.list_price) == (price, list_price)
    assert r.image_url is None


@pytest.mark.parametrize("stock,available", [(0, False), (1, True), (520, True)])
def test_stock(stock, available):
    assert cv.parse(_raw({"price-list-cl": 1000}, stock=stock), ref("1")).available is available


@pytest.mark.parametrize("stock", [None, "5", True])
def test_sin_stock_legible_es_error(stock):
    with pytest.raises(FetchError):
        cv.parse(_raw({"price-list-cl": 1000}, stock=stock), ref("1"))


@pytest.mark.parametrize(
    "raw",
    [
        "no es json",
        "[]",
        '{"error":"Ocurrió un error en el servidor","errorCode":"INTERNAL_ERROR"}',
        '{"error":"La sesión ha expirado","errorCode":"INVALID_SESSION"}',
    ],
)
def test_respuesta_rota_es_fetch_error(raw):
    with pytest.raises(FetchError):
        cv.parse(raw, ref("1"))


def test_otro_producto_es_error():
    with pytest.raises(FetchError):
        cv.parse(fixture_text("cruzverde", "descuento.json"), ref("124158"))


@pytest.mark.parametrize(
    "url,expected",
    [
        (URL, URL),
        (
            "https://cruzverde.cl/xumadol-paracetamol-1000-mg-20-comprimidos/266145.html?x=1#top",
            URL,
        ),
        (
            "http://www.cruzverde.cl/cualquier-cosa/266145.html",
            "https://www.cruzverde.cl/cualquier-cosa/266145.html",
        ),
        (
            "https://www.cruzverde.cl/elixine-teofilina-anhidra-80-mg-250-ml-%7C-cruz-verde/6031.html",
            "https://www.cruzverde.cl/elixine-teofilina-anhidra-80-mg-250-ml-%7C-cruz-verde/6031.html",
        ),
    ],
)
def test_normaliza(url, expected):
    r = cv.normalize(url)
    assert r.canonical_url == expected
    assert r.external_id == expected.rsplit("/", 1)[1].removesuffix(".html")
    assert r.variant_id == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://www.cruzverde.cl.evil.com/xumadol/266145.html",
        "https://evilcruzverde.cl/xumadol/266145.html",
        "https://www.cruzverde.cl/266145.html",  # sin slug: la SPA dice "no encontrada"
        "https://www.cruzverde.cl/medicamentos/endocrinologia/",
        "https://www.cruzverde.cl/garnier/",
        "https://www.cruzverde.cl/search?query=266145",
        "https://www.cruzverde.cl/a/b/266145.html",
        "https://www.cruzverde.cl/xumadol/266145",
        "https://www.cruzverde.cl/",
    ],
)
def test_no_matchea(url):
    assert not cv.matches(url)
    with pytest.raises(ValueError):
        cv.normalize(url)


# --- Sesión invitado (transporte simulado, sin red) -------------------------------------

DETAIL_OK = fixture_text("cruzverde", "sin_descuento.json")
INVALID = {"error": "La sesión ha expirado", "errorCode": "INVALID_SESSION"}


@pytest.fixture
def api(monkeypatch):
    """API falsa: cada login entrega una sesión nueva (s1, s2…); el detalle acepta solo
    las sesiones de `valid`. Registra las peticiones en `calls`."""
    state = {"logins": 0, "valid": set(), "calls": [], "detail": None, "login_status": 201}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append((request.method, request.url.path, request.headers.get("cookie")))
        assert request.headers["origin"] == "https://www.cruzverde.cl"
        if request.url.path == "/customer-service/login":
            await asyncio.sleep(0.01)  # deja que otras lecturas se pongan a esperar el lock
            assert json.loads(request.content) == {}
            state["logins"] += 1
            sid = f"s{state['logins']}"
            state["valid"].add(sid)
            return httpx.Response(
                state["login_status"],
                json={"authType": "guest", "salesforceToken": "no-se-guarda"},
                headers={"set-cookie": f"connect.sid={sid}; Path=/; HttpOnly; Secure"},
            )
        sid = (request.headers.get("cookie") or "").removeprefix("connect.sid=")
        if sid not in state["valid"]:
            return httpx.Response(401, json=INVALID)
        if state["detail"]:
            return state["detail"]
        return httpx.Response(200, text=DETAIL_OK)

    monkeypatch.setattr(cvmod, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(cvmod, "_session", None)
    monkeypatch.setattr(cvmod, "_session_lock", asyncio.Lock())
    return state


async def test_sin_sesion_hace_login_y_la_reutiliza(api):
    assert await cv.fetch_raw(ref("124158")) == DETAIL_OK
    assert await cv.fetch_raw(ref("124158")) == DETAIL_OK
    assert api["logins"] == 1
    assert [c[1] for c in api["calls"]] == [
        "/customer-service/login",
        "/product-service/products/detail/124158",
        "/product-service/products/detail/124158",
    ]
    assert api["calls"][1][2] == "connect.sid=s1"
    assert cvmod._session == "s1"


async def test_sesion_vencida_rehace_login_y_reintenta_una_vez(api):
    cvmod._session = "vencida"
    assert await cv.fetch_raw(ref("124158")) == DETAIL_OK
    assert api["logins"] == 1
    assert [(c[1], c[2]) for c in api["calls"]] == [
        ("/product-service/products/detail/124158", "connect.sid=vencida"),
        ("/customer-service/login", None),
        ("/product-service/products/detail/124158", "connect.sid=s1"),
    ]
    assert cvmod._session == "s1"


async def test_401_tras_un_login_nuevo_no_entra_en_bucle(api):
    api["detail"] = httpx.Response(401, json=INVALID)
    cvmod._session = "vencida"
    with pytest.raises(FetchError):
        await cv.fetch_raw(ref("124158"))
    assert api["logins"] == 1
    assert len(api["calls"]) == 3


async def test_lecturas_concurrentes_hacen_un_solo_login(api):
    cvmod._session = "vencida"
    results = await asyncio.gather(*(cv.fetch_raw(ref("124158")) for _ in range(5)))
    assert results == [DETAIL_OK] * 5
    assert api["logins"] == 1


async def test_login_fallido_es_fetch_error(api):
    api["login_status"] = 403
    with pytest.raises(FetchError):
        await cv.fetch_raw(ref("124158"))
    assert cvmod._session is None


async def test_500_es_fetch_error_y_no_not_found(api):
    # Así responde un id inexistente (y también una falla de la API).
    api["detail"] = httpx.Response(
        500, json={"error": "Ocurrió un error en el servidor", "errorCode": "INTERNAL_ERROR"}
    )
    with pytest.raises(FetchError) as exc:
        await cv.fetch_raw(ref("999999999"))
    assert not isinstance(exc.value, NotFoundError)


async def test_error_de_red_es_fetch_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    monkeypatch.setattr(cvmod, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(cvmod, "_session", None)
    monkeypatch.setattr(cvmod, "_session_lock", asyncio.Lock())
    with pytest.raises(FetchError):
        await cv.fetch_raw(ref("124158"))


def test_fixtures_sin_tokens():
    for name in (
        "descuento",
        "sin_descuento",
        "agotado",
        "receta",
        "receta_retenida",
    ):
        raw = fixture_text("cruzverde", f"{name}.json")
        assert "salesforceToken" not in raw
        assert "connect.sid" not in raw
