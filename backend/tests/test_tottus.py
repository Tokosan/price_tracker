import logging
from urllib.parse import unquote

import pytest

from tests.conftest import fixture_text
from tracker.processors import NotFoundError, find_processor
from tracker.processors.tottus import ZONES, TottusProcessor

tottus = TottusProcessor()
BASE = "https://www.tottus.cl/tottus-cl/articulo"
LECHE = f"{BASE}/128289122/leche-semidescremada-uht-surlat-1-lt/128289124"


@pytest.fixture(autouse=True)
def logger_activo(monkeypatch):
    # El fileConfig de Alembic (test_migrations) deshabilita los loggers ya creados.
    monkeypatch.setattr(logging.getLogger("tracker.processors.tottus"), "disabled", False)


def warnings(caplog):
    return [r for r in caplog.records if r.name == "tracker.processors.tottus"]


def parse(fixture, url):
    return tottus.parse(fixture_text("tottus", fixture), tottus.normalize(url))


def test_en_stock():
    r = parse("en_stock.json", LECHE)
    assert r.title == "Leche Semidescremada Surlat 1 lt"
    assert (r.price, r.list_price, r.currency, r.available) == (1190, None, "CLP", True)
    assert r.image_url == "https://media.falabella.com/tottusCL/21309174_1/public"


def test_descuento():
    r = parse("descuento.json", f"{BASE}/125312475")
    assert r.title == "Pañal Súper Premium Babysec Talla M 70 Un"
    assert (r.price, r.list_price, r.available) == (18790, 24890, True)


def test_agotado_con_precio():
    r = parse("agotado.json", f"{BASE}/111865564/alfajor-brandy-4-unidades-180gr-lds/111865565")
    assert r.title == "Alfajor Brandy"
    assert (r.price, r.list_price, r.available) == (2539, None, False)


def test_zonas_invalidas_se_ven_como_agotado():
    # Por eso el warning: la API no da error, solo dice OUT_OF_STOCK con la variante.
    r = parse("en_stock_zonas_invalidas.json", LECHE)
    assert (r.price, r.available) == (1190, False)


def test_no_encontrado():
    with pytest.raises(NotFoundError):
        parse("no_encontrado.json", f"{BASE}/999999999")


def test_producto_de_una_variante_no_ofrece_selector():
    assert (
        tottus.parse_variants(fixture_text("tottus", "en_stock.json"), tottus.normalize(LECHE))
        == []
    )


def test_zonas_fijas_del_plan():
    raw = (
        "PCL6672%2CPCL1223%2CPCL2976%2CPCL3651%2CPCL3887%2CPCL6655%2CPCL2709%2CPCL2829%2C"
        "PCL3505%2CPCL3136%2CPCL4992%2CPCL5127%2CPCL6985%2CPCL6702%2CPCL1486%2CPCL3031%2C"
        "PCL1839%2CPCL3676%2CPCL3139%2CPCL2992%2CPCL2269%2CPCL6668%2CPCL4976%2CPCL651%2C"
        "LEG_TOTTUS_DOMINICOS_1%2CPCL596%2CPCL6641%2CPCL226%2CPCL108%2CPCL2288%2CPCL3232%2C"
        "PCL3145%2CPCL1394%2CPCL5090%2CPCL5234%2CPCL2792"
    )
    assert ",".join(ZONES) == unquote(raw)
    assert len(ZONES) == 36


async def test_fetch_manda_exp_pgid_y_zonas(monkeypatch):
    calls = []

    async def fake_get_text(url, *, params=None):
        calls.append((url, list(params.items())))
        return fixture_text("tottus", "en_stock.json")

    monkeypatch.setattr("tracker.processors.falabella_platform.get_text", fake_get_text)
    await TottusProcessor().fetch_raw(tottus.normalize(LECHE))
    assert calls == [
        (
            "https://www.falabella.com/s/browse/v3/product/cl",
            [
                ("site", "tottus-cl"),
                ("productId", "128289122"),
                ("exp", "to_com"),
                ("pgid", "34"),
                ("zones", ",".join(ZONES)),
            ],
        )
    ]


async def test_warning_al_pasar_de_en_stock_a_agotado(monkeypatch, caplog):
    proc = TottusProcessor()
    answers = iter(["en_stock.json", "en_stock.json", "en_stock_zonas_invalidas.json"] * 2)

    async def fake_fetch_raw(ref):
        return fixture_text("tottus", next(answers))

    monkeypatch.setattr(proc, "fetch_raw", fake_fetch_raw)
    ref = proc.normalize(LECHE)
    with caplog.at_level(logging.WARNING, logger="tracker.processors.tottus"):
        assert (await proc.fetch(ref)).available
        assert (await proc.fetch(ref)).available
        assert not warnings(caplog)
        assert not (await proc.fetch(ref)).available
    assert len(warnings(caplog)) == 1
    assert "revisa las zonas" in warnings(caplog)[0].getMessage()


async def test_sin_warning_si_nunca_se_vio_en_stock(monkeypatch, caplog):
    proc = TottusProcessor()

    async def fake_fetch_raw(ref):
        return fixture_text("tottus", "agotado.json")

    monkeypatch.setattr(proc, "fetch_raw", fake_fetch_raw)
    ref = proc.normalize(f"{BASE}/111865564/alfajor/111865565")
    with caplog.at_level(logging.WARNING, logger="tracker.processors.tottus"):
        await proc.fetch(ref)
        await proc.fetch(ref)
    assert not warnings(caplog)


@pytest.mark.parametrize(
    ("url", "pid", "sku", "canonical"),
    [
        (f"{BASE}/125312475", "125312475", "", f"{BASE}/125312475"),
        (f"{LECHE}/?x=1#y", "128289122", "128289124", LECHE),
        (
            "http://tottus.cl/tottus-cl/articulo/128289122/Leche/128289124",
            "128289122",
            "128289124",
            f"{BASE}/128289122/Leche/128289124",
        ),
        (
            "HTTPS://WWW.TOTTUS.CL/TOTTUS-CL/ARTICULO/125312475",
            "125312475",
            "",
            f"{BASE}/125312475",
        ),
    ],
)
def test_normaliza_url(url, pid, sku, canonical):
    assert tottus.matches(url)
    ref = tottus.normalize(url)
    assert (ref.external_id, ref.variant_id, ref.canonical_url) == (pid, sku, canonical)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tottus.cl.evil.com/tottus-cl/articulo/128289122",
        "https://eviltottus.cl/tottus-cl/articulo/128289122",
        "https://www.tottus.cl/tottus-cl/lista/CATG27055/Leches",
        "https://www.tottus.cl/tottus-cl/buscar?Ntt=leche",
        "https://www.tottus.cl/tottus-cl/product/128289122",
        "https://www.tottus.cl/tottus-cl/articulo/abc",
        "https://www.falabella.com/tottus-cl/articulo/128289122",
        # Hoy redirige a /tottus-cl/not-found.
        "https://tottus.falabella.com/tottus-cl/articulo/128289122",
    ],
)
def test_no_matchea(url):
    assert not tottus.matches(url)


def test_registrado():
    assert find_processor(f"{BASE}/125312475").name == "tottus"
    assert tottus.domain() == "www.falabella.com"
