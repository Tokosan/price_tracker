import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.sodimac import SodimacProcessor

sodimac = SodimacProcessor()
BASE = "https://www.sodimac.cl/sodimac-cl/articulo"
PUERTA = f"{BASE}/128506383/puerta-exterior-madera-pino-oregon-80x200-cm-modelo-4-natural"


def parse(fixture, url):
    return sodimac.parse(fixture_text("sodimac", fixture), sodimac.normalize(url))


def test_solo_cmr_usa_precio_internet():
    # cmrPrice 51.990 e internetPrice 71.390, sin precio tachado.
    r = parse("solo_cmr.json", f"{BASE}/110033778/taladro/110033784")
    assert r.title == "Taladro Inalámbrico Percutor 10 mm 20 V/1 Batería"
    assert (r.price, r.list_price, r.currency, r.available) == (71390, None, "CLP", True)
    assert r.image_url == "https://media.falabella.com/sodimacCL/5417236_001/public"


def test_descuento_de_vendedor_externo():
    # cmrPrice 169.990, eventPrice 184.990, normalPrice tachado 299.990 (Tus Herramientas).
    r = parse("descuento_tercero.json", f"{BASE}/144212237/kit/144212238")
    assert r.title == "Kit Makita Taladro Percutor + Atornillador Makita CLX228"
    assert (r.price, r.list_price, r.available) == (184990, 299990, True)


@pytest.mark.parametrize(
    ("sku", "label", "price"),
    [("128506384", "80X200CM", 369990), ("128551885", "100X210CM", 394990)],
)
def test_cada_medida_tiene_su_precio(sku, label, price):
    r = parse("medidas.json", f"{PUERTA}/{sku}")
    assert r.title == f"Puerta Exterior Madera pino oregón 80x200 cm Modelo 4 Natural ({label})"
    assert (r.price, r.list_price, r.available) == (price, None, True)


def test_variantes_por_medida():
    raw = fixture_text("sodimac", "medidas.json")
    url = f"{PUERTA}/128506384"
    variants = sodimac.parse_variants(raw, sodimac.normalize(url))
    assert len(variants) == 21
    assert (variants[0].url, variants[0].variant_id, variants[0].selected) == (
        url,
        "128506384",
        True,
    )
    assert variants[0].label == "80X200CM: $369.990"
    by_sku = {v.variant_id: v for v in variants}
    assert by_sku["128552073"].label == "100X200CM: $389.990"
    assert by_sku["128552073"].url == f"{PUERTA}/128552073"
    assert len({v.label for v in variants}) == 21  # cada medida se distingue
    for v in variants:
        assert sodimac.normalize(v.url).variant_id == v.variant_id


def test_link_sin_sku_fija_la_medida_actual():
    raw = fixture_text("sodimac", "medidas.json")
    current = sodimac.parse_variants(raw, sodimac.normalize(f"{BASE}/128506383"))[0]
    assert current.selected
    assert (current.variant_id, current.url) == ("128506336", f"{PUERTA}/128506336")


def test_agotado_con_precio():
    r = parse("agotado.json", f"{BASE}/122895155/oxicorte/122895156")
    assert r.title == "Equipo De Oxicorte Completo Industrial 17 Piezas Makawa"
    assert (r.price, r.list_price, r.available) == (160300, 264990, False)


def test_agotado_sin_variantes_no_tiene_precio():
    r = parse("agotado_sin_variantes.json", f"{BASE}/110197845/riel/110197846")
    assert r.title == "Riel para cortina aluminio 2 m"
    assert (r.price, r.available) == (None, False)
    assert sodimac.sold_out_without_price is True


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("no_encontrado.json", f"{BASE}/999999999")


@pytest.mark.parametrize(
    ("url", "pid", "sku", "canonical"),
    [
        (f"{BASE}/128506383", "128506383", "", f"{BASE}/128506383"),
        (f"{PUERTA}/128506384/", "128506383", "128506384", f"{PUERTA}/128506384"),
        (
            "http://sodimac.cl/sodimac-cl/articulo/110033778/Taladro/110033784?exp=so_com#x",
            "110033778",
            "110033784",
            f"{BASE}/110033778/Taladro/110033784",
        ),
        (
            "HTTPS://WWW.SODIMAC.CL/SODIMAC-CL/ARTICULO/128506383",
            "128506383",
            "",
            f"{BASE}/128506383",
        ),
    ],
)
def test_normaliza_url(url, pid, sku, canonical):
    assert sodimac.matches(url)
    ref = sodimac.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (pid, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.sodimac.cl.evil.com/sodimac-cl/articulo/128506383",
        "https://evilsodimac.cl/sodimac-cl/articulo/128506383",
        "https://www.sodimac.cl/sodimac-cl/lista/CATG34399/Taladros-Inalambricos",
        "https://www.sodimac.cl/sodimac-cl/buscar?Ntt=taladro",
        "https://www.sodimac.cl/sodimac-cl/product/128506383",
        "https://www.sodimac.cl/sodimac-cl/articulo/abc",
        "https://www.falabella.com/sodimac-cl/articulo/128506383",
        # Hoy redirige a /sodimac-cl/not-found.
        "https://sodimac.falabella.com/sodimac-cl/articulo/128506383",
    ],
)
def test_no_matchea(url):
    assert not sodimac.matches(url)


def test_registrado_sin_chocar_con_falabella():
    assert find_processor(f"{BASE}/128506383").name == "sodimac"
    assert find_processor("https://www.falabella.com/falabella-cl/product/80758957").name == (
        "falabella"
    )


async def test_fetch_pide_la_api_de_falabella_con_site_sodimac(monkeypatch):
    calls = []

    async def fake_get_text(url, *, params=None):
        calls.append((url, list(params.items())))
        return "{}"

    monkeypatch.setattr("tracker.processors.falabella_platform.get_text", fake_get_text)
    await sodimac.fetch_raw(sodimac.normalize(f"{PUERTA}/128506384"))
    assert calls == [
        (
            "https://www.falabella.com/s/browse/v3/product/cl",
            [("site", "sodimac-cl"), ("productId", "128506383")],
        )
    ]
    assert sodimac.domain() == "www.falabella.com"
