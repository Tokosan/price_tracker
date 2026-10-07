"""Bold y Belsport (base SAP Commerce / API OCC).

Fixtures reales de `products/<código>?fields=FULL`, con `reviews` vaciado (traía el nombre
de pila de quienes opinaron).
"""

import httpx
import pytest

from tests.conftest import fixture_text
from tracker.processors import FetchError, NotFoundError, find_processor
from tracker.processors.belsport import BelsportProcessor
from tracker.processors.bold import BoldProcessor

bold = BoldProcessor()
belsport = BelsportProcessor()
PATH = "https://www.bold.cl/Categories/Genero/Hombre/Calzado-Hombre/Zapatillas-Hombre"
FORUM = f"{PATH}/Forum2000-Zapatillas-adidas-Unisex-Negro/p/ADJR1121"
AVA = f"{PATH}/Ava-X-Zapatillas-Nike-Negro/p/NIHM9697002"
COURT = (
    "https://www.belsport.cl/Categories/Genero/Mujer/Zapatillas-Mujer/Zapatillas-Urbanas-Mujer/"
    "Zapatillas-Nike-Mujer-Court-Vision-Low-Blancas/p/NIDH3158100"
)


def parse(proc, fixture, url):
    return proc.parse(fixture_text(proc.name, fixture), proc.normalize(url))


def test_base_sigue_cualquier_talla():
    # El stock del base dice outOfStock, pero 4 de 5 tallas tienen stock online.
    r = parse(bold, "base_tallas.json", FORUM)
    assert r.title == "Forum2000 Zapatillas adidas Unisex Negro"
    assert (r.price, r.list_price, r.currency, r.available) == (47990, 119990, "CLP", True)
    assert r.image_url.startswith("https://api-prd.ynk.cl/medias/300Wx300H-BOLD-ADJR1121-VIEW1")


def test_talla_agotada():
    r = parse(bold, "talla_agotada.json", f"{FORUM}070")
    assert r.title == "Forum2000 Zapatillas adidas Unisex Negro (talla US 7 UNSX)"
    assert (r.price, r.list_price, r.available) == (47990, 119990, False)


def test_agotado_online_aunque_haya_stock_en_tiendas():
    # Todas las tallas outOfStock online; physicalStockLevelStatus dice inStock (tiendas).
    r = parse(bold, "agotado.json", AVA)
    assert (r.price, r.list_price, r.available) == (79990, 132990, False)


def test_lowstock_cuenta_como_disponible():
    r = parse(belsport, "base_tallas.json", COURT)
    assert r.title == "Zapatillas Nike Mujer Court Vision Low Blancas"
    assert (r.price, r.list_price, r.available) == (52990, 74990, True)


def test_variantes_desde_el_base_y_desde_una_talla():
    raw = fixture_text("bold", "base_tallas.json")
    variants = bold.parse_variants(raw, bold.normalize(FORUM))
    assert [v.label for v in variants] == [
        "Cualquier talla",
        "Talla US 7 UNSX: $47.990 (agotada)",
        "Talla US 8 UNSX: $47.990",
        "Talla US 8.5 UNSX: $47.990",
        "Talla US 9 UNSX: $47.990",
        "Talla US 9.5 UNSX: $47.990",
    ]
    assert variants[0].selected and variants[0].url == FORUM
    assert (variants[1].external_id, variants[1].url) == ("ADJR1121070", f"{FORUM}070")
    for v in variants:
        assert bold.normalize(v.url).external_id == v.external_id

    raw = fixture_text("bold", "talla_agotada.json")
    variants = bold.parse_variants(raw, bold.normalize(f"{FORUM}070"))
    assert (variants[0].external_id, variants[0].selected) == ("ADJR1121070", True)
    anyone = next(v for v in variants if v.label == "Cualquier talla")
    assert (anyone.external_id, anyone.url) == ("ADJR1121", FORUM)


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse(bold, "no_encontrado.json", f"{PATH}/x/p/NOEXISTE123")


def test_respuesta_de_otro_producto():
    with pytest.raises(FetchError):
        parse(bold, "base_tallas.json", AVA)


async def test_fetch_400_desconocido_es_no_encontrado(monkeypatch):
    body = fixture_text("bold", "no_encontrado.json")

    def handler(request):
        assert request.url.path == "/rest/v2/boldb2cstore/products/NOEXISTE123"
        assert request.url.params["fields"] == "FULL"
        return httpx.Response(400, text=body)

    real = httpx.AsyncClient

    def client(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("tracker.processors.sapcommerce.httpx.AsyncClient", client)
    with pytest.raises(NotFoundError):
        await bold.fetch_raw(bold.normalize(f"{PATH}/x/p/NOEXISTE123"))


@pytest.mark.parametrize(
    ("proc", "url", "code", "canonical"),
    [
        (bold, FORUM, "ADJR1121", FORUM),
        (bold, f"{FORUM}080?utm=x#y", "ADJR1121080", f"{FORUM}080"),
        (bold, "https://bold.cl/p/adjr1121", "ADJR1121", "https://www.bold.cl/p/ADJR1121"),
        (belsport, COURT, "NIDH3158100", COURT),
    ],
)
def test_normaliza_url(proc, url, code, canonical):
    assert proc.matches(url)
    ref = proc.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (code, "", canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bold.cl.evil.com/x/p/ADJR1121",
        "https://evilbold.cl/x/p/ADJR1121",
        "https://www.bold.cl/Categories/Marcas/Nike/c/boldMarcasNike",
        "https://www.bold.cl/search?q=zapatilla",
        "https://www.bold.cl/",
        "https://www.belsport.cl/x/p/ADJR1121/otra",
    ],
)
def test_no_matchea(url):
    assert not bold.matches(url)
    assert not belsport.matches(url)


def test_registrados_por_tienda():
    assert find_processor(FORUM).name == "bold"
    assert find_processor(COURT).name == "belsport"
