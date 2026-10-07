"""Comprobaciones comunes a los tests de las tiendas de ropa en VTEX (`VtexApparelProcessor`)."""

from urllib.parse import quote

import pytest

from tests.conftest import fixture_text
from tracker.processors import ProductRef, find_processor
from tracker.processors.vtex_apparel import VtexApparelProcessor


def parse(proc: VtexApparelProcessor, fixture: str, url: str):
    return proc.parse(fixture_text(proc.name, fixture), proc.normalize(url))


def variants(proc: VtexApparelProcessor, fixture: str, url: str):
    return proc.parse_variants(fixture_text(proc.name, fixture), proc.normalize(url))


def labels(proc: VtexApparelProcessor, fixture: str, url: str) -> list[str]:
    return [v.label for v in variants(proc, fixture, url)]


def check_urls(proc: VtexApparelProcessor, slug: str, account: str) -> None:
    """Normalización, `skuId` y que no matchee otros dominios ni rutas que no son fichas."""
    host = proc.host
    bare = host.removeprefix("www.")
    canon = f"https://{host}/{quote(slug)}/p"
    assert proc.domain() == f"{account}.vtexcommercestable.com.br"
    assert find_processor(canon) is proc
    for url, sku in [
        (canon, ""),
        (f"http://{bare}/{quote(slug)}/p/", ""),
        (f"https://{host.upper()}/{quote(slug).upper()}/p?utm_source=x#top", ""),
        (f"{canon}?skuId=12345", "12345"),
        (f"{canon}?utm_source=x&skuId=12345", "12345"),
        (f"{canon}?skuId=abc", ""),
    ]:
        ref = proc.normalize(url)
        assert ref == ProductRef(slug, canon + (f"?skuId={sku}" if sku else ""), sku), url
    for url in [
        f"https://{host}/",
        f"https://{host}/hombre/zapatillas",
        f"https://{host}/{quote(slug)}",
        f"https://{host}/busqueda?ft=polera",
        f"https://{host}/../p",
        f"https://{host}.evil.com/{quote(slug)}/p",
        f"https://evil-{bare}/{quote(slug)}/p",
        f"https://{bare}.evil.com/{quote(slug)}/p",
        f"ftp://{host}/{quote(slug)}/p",
    ]:
        assert not proc.matches(url), url
    with pytest.raises(ValueError):
        proc.normalize(f"https://{host}/hombre/zapatillas")
