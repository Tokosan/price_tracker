import json
import re

import httpx
import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, ProductRef, find_processor
from tracker.processors.ahumada import AhumadaProcessor, pdp_summary

ahumada = AhumadaProcessor()
HOST = "https://www.farmaciasahumada.cl"
ISDIN = f"{HOST}/protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html"
REFLEXAN = f"{HOST}/reflexan-10-mg-x-20-comprimidos-recubiertos-6.html"
TETINA = f"{HOST}/tetina-pigeon-repuesto-boca-standard-talla-m-2-un-89871.html"
URIAGE = f"{HOST}/protector-solar-uriage-bariesun-100-fps-50-50-ml-88464.html"


def parse(fixture, url):
    return ahumada.parse(fixture_text("ahumada", fixture), ahumada.normalize(url))


def _con(fixture, cambio):
    data = json.loads(fixture_text("ahumada", fixture))
    cambio(data)
    return json.dumps(data)


def test_descuento_trae_el_precio_normal():
    r = parse("isdin_descuento.json", ISDIN)
    assert (r.title, r.price, r.list_price, r.currency, r.available) == (
        "Protector Solar Isdin Fusion Water Magic FPS 50 50 mL",
        13859,
        23099,
        "CLP",
        True,
    )
    assert isinstance(r.price, int) and isinstance(r.list_price, int)
    assert r.image_url.startswith(f"{HOST}/dw/image/")


def test_en_stock_sin_descuento():
    r = parse("reflexan_en_stock.json", REFLEXAN)
    assert r.title == "Reflexan 10 mg x 20 Comprimidos Recubiertos"
    assert (r.price, r.list_price, r.available) == (13719, None, True)


def test_agotado_en_santiago_sale_del_boton_de_la_ficha():
    # Product-Variation dice "In Stock" igual; la ficha muestra "Producto sin stock".
    raw = fixture_text("ahumada", "uriage_agotado_santiago.json")
    data = json.loads(raw)
    assert data["pdp"]["commune"] == "Santiago"
    assert data["variation"]["product"]["available"] is True
    assert data["variation"]["product"]["availability"]["messages"] == ["In Stock"]
    r = ahumada.parse(raw, ahumada.normalize(URIAGE))
    assert r.title == "Protector Solar Uriage Bariesun 100 FPS 50 50 mL"
    assert (r.price, r.list_price, r.available) == (14759, 24599, False)


def test_en_stock_en_santiago_aunque_no_en_la_zona_por_defecto():
    # El 89871 sale sin stock sin comuna (Las Condes) y con stock en Santiago.
    r = parse("tetina_en_stock_santiago.json", TETINA)
    assert (r.price, r.list_price, r.available) == (7799, None, True)


def test_stock_de_otra_comuna_es_error_de_lectura():
    def otra(data):
        data["pdp"]["commune"] = "Las Condes"

    with pytest.raises(FetchError):
        ahumada.parse(_con("tetina_en_stock_santiago.json", otra), ahumada.normalize(TETINA))


def test_ignora_el_precio_familia_ahumada():
    def club(data):
        price = data["variation"]["product"]["price"]
        price["hasFamiliaAhumadaPrice"] = True
        price["familiaAhumadaPriceForCart"] = {"value": 9999}

    r = ahumada.parse(_con("isdin_descuento.json", club), ahumada.normalize(ISDIN))
    assert (r.price, r.list_price) == (13859, 23099)


def test_precio_0_no_es_precio():
    def cero(data):
        data["variation"]["product"]["price"]["sales"]["value"] = 0

    r = ahumada.parse(_con("reflexan_en_stock.json", cero), ahumada.normalize(REFLEXAN))
    assert r.price is None


def test_no_es_ficha_de_producto():
    def contenido(data):
        data["pdp"] = {"action": "Page-Show", "add_to_cart": None}

    with pytest.raises(NotFoundError):
        ahumada.parse(_con("reflexan_en_stock.json", contenido), ahumada.normalize(REFLEXAN))


@pytest.mark.parametrize(
    "cambio",
    [
        lambda d: d["pdp"].update(add_to_cart=None),
        lambda d: d["pdp"].update(add_to_cart='<button class="add-to-cart" data-pid="6">'),
        lambda d: d.pop("pdp"),
        lambda d: d.update(variation={"error": "x"}),
        lambda d: d["variation"]["product"].update(id="7"),
    ],
    ids=["sin-boton", "boton-sin-stock", "sin-pdp", "sin-producto", "otro-producto"],
)
def test_respuesta_incompleta_es_error_de_lectura(cambio):
    with pytest.raises(FetchError):
        ahumada.parse(_con("reflexan_en_stock.json", cambio), ahumada.normalize(REFLEXAN))


def test_respuesta_que_no_es_json():
    with pytest.raises(FetchError):
        ahumada.parse("<html>error</html>", ahumada.normalize(REFLEXAN))


def test_pdp_summary_toma_el_boton_del_producto_y_no_los_de_carruseles():
    html = (
        '<div class="page" data-action="Product-Show" data-querystring="pid=6" >'
        '<span class="commune"> Santiago </span>'
        '<button class="btn product-tile-add-to-cart" data-pid="7" data-is-unavailable="false">'
        '<button class="add-to-cart-global btn" data-pid="6">'
        '<button class="add-to-cart btn btn-primary"\n data-pid="6"\n'
        ' data-is-unavailable="true"\n disabled>'
    )
    summary = pdp_summary(html, "6")
    assert (summary["action"], summary["commune"]) == ("Product-Show", "Santiago")
    assert 'data-is-unavailable="true"' in summary["add_to_cart"]
    assert pdp_summary(html, "60")["add_to_cart"] is None
    assert pdp_summary("<html></html>", "6") == {
        "action": None,
        "commune": None,
        "add_to_cart": None,
    }


@pytest.mark.parametrize(
    "div",
    [
        '<div class="page" data-action="Product-Show">',
        '<div data-action="Product-Show" class="page">',
        '<div id="x" class="page product" data-querystring="pid=6" data-action="Product-Show">',
        '<div class="js page" data-action="Product-Show">',
    ],
)
def test_pdp_summary_tolera_orden_y_clases_del_div_page(div):
    assert pdp_summary(div, "6")["action"] == "Product-Show"


def test_pdp_summary_no_toma_data_action_de_otro_div():
    html = '<div class="pagination" data-action="Search-Show"><div class="page-x">'
    assert pdp_summary(html, "6")["action"] is None


def test_pdp_summary_de_la_ficha_real_con_santiago():
    summary = pdp_summary(fixture_text("ahumada", "ficha_tetina_santiago.html"), "89871")
    assert (summary["action"], summary["commune"]) == ("Product-Show", "Santiago")
    assert 'data-is-unavailable="false"' in summary["add_to_cart"]


def test_sin_variantes():
    assert ahumada.supports_variants is False
    raw = fixture_text("ahumada", "isdin_descuento.json")
    assert ahumada.parse_variants(raw, ahumada.normalize(ISDIN)) == []


@pytest.mark.parametrize(
    "url",
    [
        ISDIN,
        "https://farmaciasahumada.cl/protector-solar-isdin-fusion-water-magic-fps-50-50-ml-92197.html",
        "http://www.farmaciasahumada.cl/Protector-Solar-Isdin-Fusion-Water-Magic-FPS-50-50-mL-92197.html",
        f"{ISDIN}?quantity=1&dwvar_92197_x=y#tab",
    ],
)
def test_normaliza_url(url):
    assert ahumada.normalize(url) == ProductRef("92197", ISDIN)


def test_pid_corto_y_slug_con_parentesis():
    assert ahumada.normalize(REFLEXAN) == ProductRef("6", REFLEXAN)
    pampers = f"{HOST}/panal-pampers-proteccion-insuperable-talla-m-%286-10-kg%29-62-un-97257.html"
    assert ahumada.normalize(pampers) == ProductRef("97257", pampers)


def test_pide_product_variation_de_su_sitio():
    assert ahumada.controller_url("Product-Variation") == (
        f"{HOST}/on/demandware.store/Sites-ahumada-cl-Site/default/Product-Variation"
    )


def test_matchea_solo_fichas_de_su_dominio():
    assert find_processor(ISDIN).name == "ahumada"
    assert not ahumada.matches(f"{HOST}/")
    assert not ahumada.matches(f"{HOST}/belleza/proteccion-solar/rostro")
    assert not ahumada.matches(f"{HOST}/search?q=protector")
    assert not ahumada.matches(f"{HOST}/belleza/protector-solar-92197.html")  # dos segmentos
    assert not ahumada.matches(f"{HOST}/protector-solar.html")  # sin pid
    assert not ahumada.matches("https://www.farmaciasahumada.cl.evil.com/protector-92197.html")
    assert not ahumada.matches("https://evilfarmaciasahumada.cl/protector-92197.html")
    assert not ahumada.matches("https://www.hites.com/protector-solar-92197001.html")
    assert not ahumada.matches("ftp://www.farmaciasahumada.cl/protector-92197.html")
    assert not ahumada.matches(f"{HOST}/protector-solar-123456789.html")  # pid de 9 dígitos


# --- Sesión con la comuna Santiago (transporte falso de httpx, sin red) ---

FICHA = fixture_text("ahumada", "ficha_tetina_santiago.html")
SAVE_ZONE = fixture_text("ahumada", "save_zone_santiago.json")
VARIATION = json.dumps(
    json.loads(fixture_text("ahumada", "tetina_en_stock_santiago.json"))["variation"]
)
SANTIAGO = re.compile(r'(<span class="commune">\s*)Santiago(\s*</span>)')
DISPONIBLE = re.compile(r'(data-pid="89871"\s+data-is-unavailable=)"false"')


def _sin_zona(ficha: str) -> str:
    """La ficha sin zona en la sesión: la tienda usa Las Condes, donde el 89871 no tiene stock."""
    ficha = SANTIAGO.sub(r"\1Las Condes\2", ficha)
    return DISPONIBLE.sub(r'\1"true"', ficha)


def test_la_ficha_de_prueba_sin_zona_cambia_comuna_y_stock():
    assert len(SANTIAGO.findall(FICHA)) == 2  # cabecera de escritorio y de móvil
    assert DISPONIBLE.search(FICHA)
    summary = pdp_summary(_sin_zona(FICHA), "89871")
    assert summary["commune"] == "Las Condes"
    assert 'data-is-unavailable="true"' in summary["add_to_cart"]


class FakeAhumada:
    """Imita a la tienda: la zona vive en la sesión (cookie `dwsid`)."""

    def __init__(self, save_zone=SAVE_ZONE, ficha_status=200, keeps_zone=True):
        self.save_zone = save_zone
        self.ficha_status = ficha_status
        self.keeps_zone = keeps_zone
        self.zoned: dict[str, bool] = {}  # dwsid → tiene zona
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        cookies = dict(
            part.strip().split("=", 1)
            for part in request.headers.get("cookie", "").split(";")
            if "=" in part
        )
        sid = cookies.get("dwsid", "")
        if path == "/":
            sid = f"s{len(self.zoned) + 1}"
            self.zoned[sid] = False
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": f"dwsid={sid}"})
        if path.endswith("/Stores-SaveZone"):
            form = dict(httpx.QueryParams(request.content.decode()))
            assert request.method == "POST"
            assert form == {"state": "Región Metropolitana", "city": "Santiago"}
            if sid in self.zoned and self.keeps_zone:
                self.zoned[sid] = True
            return httpx.Response(200, text=self.save_zone)
        if path.endswith("/Product-Variation"):
            assert request.url.params["pid"] == "89871"
            return httpx.Response(200, text=VARIATION)
        if path.endswith("-89871.html"):
            if self.ficha_status != 200:
                return httpx.Response(self.ficha_status, text="no")
            return httpx.Response(200, text=FICHA if self.zoned.get(sid) else _sin_zona(FICHA))
        return httpx.Response(500, text="ruta inesperada")

    def count(self, suffix: str) -> int:
        return sum(c.endswith(suffix) for c in self.calls)


def _proc(fake: FakeAhumada) -> AhumadaProcessor:
    proc = AhumadaProcessor()
    proc.transport = httpx.MockTransport(fake)
    return proc


async def _read(proc: AhumadaProcessor):
    ref = proc.normalize(TETINA)
    return proc.parse(await proc.fetch_raw(ref), ref)


async def test_lee_la_ficha_con_la_comuna_santiago():
    fake = FakeAhumada()
    r = await _read(_proc(fake))
    assert (r.price, r.available) == (7799, True)
    assert fake.calls == [
        "GET /",
        "POST /on/demandware.store/Sites-ahumada-cl-Site/default/Stores-SaveZone",
        "GET /tetina-pigeon-repuesto-boca-standard-talla-m-2-un-89871.html",
        "GET /on/demandware.store/Sites-ahumada-cl-Site/default/Product-Variation",
    ]


async def test_reutiliza_la_sesion():
    fake = FakeAhumada()
    proc = _proc(fake)
    await _read(proc)
    await _read(proc)
    assert fake.count("Stores-SaveZone") == 1


async def test_sesion_vencida_se_recrea_y_reintenta_una_vez():
    fake = FakeAhumada()
    proc = _proc(fake)
    await _read(proc)
    fake.zoned.clear()  # la tienda olvidó la sesión: la ficha vuelve a Las Condes
    r = await _read(proc)
    assert r.available is True
    assert fake.count("Stores-SaveZone") == 2
    assert fake.count("-89871.html") == 3


async def test_si_la_ficha_nunca_refleja_la_zona_es_error_no_agotado():
    fake = FakeAhumada(keeps_zone=False)
    proc = _proc(fake)
    with pytest.raises(FetchError, match="Las Condes"):
        await proc.fetch_raw(proc.normalize(TETINA))
    assert fake.count("-89871.html") == 2  # un reintento, no más
    assert fake.count("Product-Variation") == 0


@pytest.mark.parametrize(
    "save_zone",
    [
        SAVE_ZONE.replace("inventario_santiago", "inventario_lascondes"),
        SAVE_ZONE.replace('"success": true', '"success": false'),
        '{"success": true}',
        "<html>error</html>",
    ],
    ids=["otra-zona", "sin-exito", "sin-zona", "no-json"],
)
async def test_zona_no_confirmada_es_error_de_lectura(save_zone):
    fake = FakeAhumada(save_zone=save_zone)
    proc = _proc(fake)
    with pytest.raises(FetchError):
        await proc.fetch_raw(proc.normalize(TETINA))
    assert fake.count("-89871.html") == 0


async def test_ficha_inexistente_es_not_found():
    proc = _proc(FakeAhumada(ficha_status=404))
    with pytest.raises(NotFoundError):
        await proc.fetch_raw(proc.normalize(TETINA))
