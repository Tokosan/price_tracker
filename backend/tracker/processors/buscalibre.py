"""Procesador de Buscalibre Chile (www.buscalibre.cl, librería online, plataforma propia).

Se lee la ficha HTML, que no tiene antibots. La URL es `/<slug>/<isbn>/p/<id>` (libros,
libros digitales y audiolibros): lo que identifica al producto es el `<id>` después de
`/p/`; con otro slug o ISBN la tienda redirige a la URL correcta. Cada formato (tapa
dura, tapa blanda, otra edición) tiene su propio ISBN y su propia ficha.

La ficha ofrece una o más opciones de compra (`div.opcionPrecio` en `#opciones`): el
libro nuevo (de stock en Chile o importado: "Origen: Estados Unidos", con un plazo de
semanas) y, a veces, ejemplares usados de terceros. Cada opción trae un JSON en
`data-despacho-payload` con su precio (`precio_moneda_raw`, el grande de la ficha), el
tachado (`precio_tachado_moneda_raw`, solo si `mostrar_descuento`) y si es usada
(`usado`). Un libro importado o en preventa se puede comprar: cuenta como disponible.
El tachado de un importado (`importacion` = 1) no es un precio real, sino una fórmula de
cerca del doble del precio: no se guarda como `list_price`.

El modo va en `variant_id` (y en `?modo=` de la URL), como en Solotodo: `""` (por
defecto) cuenta solo las opciones nuevas; `todos` incluye los usados. Se sigue la más
barata de las que cuenta el modo.

Sin opciones de compra, la ficha muestra "Sin Stock" y el botón `#noti-agotado`
("Avisarme al correo…"), y el JSON-LD no trae `offers`: es un agotado real sin precio
(`sold_out_without_price`). Si no hay opciones ni esa marca, o si el JSON-LD sí trae
`offers` con precio, es un error de lectura.
"""

import html as htmllib
import json
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import find_ld_product, to_minor

# /<slug>/<isbn o id>/p/<id>. Búsquedas (/libros/search/), categorías (/libros/ficcion) y
# listas (/…_t.html) no matchean. Solo Chile: los otros países (.com, .com.ar…) tienen
# otros precios y monedas.
_URL_RE = re.compile(
    r"^https?://(?:www\.)?buscalibre\.cl/([a-z0-9][a-z0-9-]*)/([0-9a-z-]+)/p/(\d+)/?(?:[?#].*)?$",
    re.I,
)
_OPTION_RE = re.compile(
    r"<div\s+class=\"opcionPrecio\b[^\"]*\"[^>]*?\sdata-despacho-payload=\"([^\"]*)\"", re.S
)
_SOLD_OUT_RE = re.compile(r"id=\"noti-agotado\"")
_OG_TYPE_RE = re.compile(r"<meta\s+property=\"og:type\"\s+content=\"([^\"]*)\"", re.I)
_TITLE_RE = re.compile(r"<p\s+class=\"tituloProducto\"\s+title=\"([^\"]*)\"")

# Modos (van en `variant_id` y en `?modo=` de la URL).
MODES = {
    "": "Solo nuevos",
    "todos": "Incluye usados",
}


class BuscalibreProcessor(Processor):
    name = "buscalibre"
    label = "Buscalibre"
    check_interval = timedelta(hours=6)
    # Sin opciones de compra y con la marca "Sin Stock" es un agotado real (ver `parse`).
    sold_out_without_price = True
    home_url = "https://www.buscalibre.cl/"
    example_url = "https://www.buscalibre.cl/libro-proyecto-hail-mary/9789566190448/p/62884122"
    platform = "HTML de la ficha (plataforma propia)"
    supports_variants = True
    supports_list_price = True
    variants_title = "¿Qué ofertas considerar?"
    variants_hint = (
        "Algunos libros también se venden usados, por terceros. Cada opción se sigue por "
        "separado: marca las que quieras."
    )
    notes = (
        "Solo buscalibre.cl. Cada formato o edición (tapa dura, tapa blanda, otro ISBN) tiene "
        "su propio link. Los libros importados (envío desde el extranjero, con un plazo de "
        "semanas) y las preventas cuentan como disponibles. En los importados no se guarda el "
        'precio "antes": el que muestra la tienda es de referencia (cerca del doble). Por '
        "defecto solo cuenta libros nuevos; "
        "también puedes seguir el más barato incluidos los usados."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Buscalibre")
        slug, code, product_id = m.group(1).lower(), m.group(2), str(int(m.group(3)))
        mode = (parse_qs(urlsplit(url).query).get("modo") or [""])[0].lower()
        if mode not in MODES:
            mode = ""
        return ProductRef(product_id, _url(f"/{slug}/{code}/p/{product_id}", mode), mode)

    def domain(self) -> str:
        return "www.buscalibre.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url.split("?", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product, options = _load(raw, ref)
        best = _best(options, ref.variant_id)
        if not options and not _SOLD_OUT_RE.search(raw):
            # Sin opciones ni la marca de agotado: el HTML cambió, no es un agotado (si no,
            # `sold_out_without_price` lo dejaría pasar y avisaría OUT_OF_STOCK).
            raise FetchError("la ficha de Buscalibre no trae opciones de compra ni 'Sin Stock'")
        if not options and _ld_has_price(product):
            raise FetchError("la ficha no trae opciones de compra, pero el JSON-LD tiene precio")
        title = _TITLE_RE.search(raw)
        image = product.get("image")
        return ScrapeResult(
            title=(
                product.get("name") or (htmllib.unescape(title.group(1)) if title else "")
            ).strip(),
            price=best[0] if best else None,
            list_price=best[1] if best else None,
            currency="CLP",
            available=best is not None,
            image_url=image if isinstance(image, str) else None,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Los dos modos con su precio de hoy (aunque uno no tenga ofertas)."""
        product, options = _load(raw, ref)
        if not options:
            return []
        # La URL del JSON-LD es la de la tienda: corrige un slug o ISBN pegado mal.
        path = _ld_path(product, ref) or urlsplit(ref.canonical_url).path
        out: list[Variant] = []
        seen: set = set()
        for mode, label in MODES.items():
            best = _best(options, mode)
            # Si "todos" cuenta lo mismo que "solo nuevos", no se ofrece (salvo que sea el del link).
            key = best[0] if best else None
            if key in seen and mode != ref.variant_id:
                continue
            seen.add(key)
            detail = f"${best[0]:,}".replace(",", ".") if best else "sin ofertas hoy"
            out.append(
                Variant(
                    url=_url(path, mode),
                    label=f"{label}: {detail}",
                    external_id=ref.external_id,
                    variant_id=mode,
                    selected=mode == ref.variant_id,
                )
            )
        return out

    def variant_label(self, external_id: str, variant_id: str) -> str:
        return MODES.get(variant_id, "")


def _url(path: str, mode: str) -> str:
    return f"https://www.buscalibre.cl{path}" + (f"?modo={mode}" if mode else "")


def _load(raw: str, ref: ProductRef) -> tuple[dict, list[dict]]:
    """(Product del JSON-LD, payloads de las opciones de compra)."""
    product = find_ld_product(raw)
    og_type = _OG_TYPE_RE.search(raw)
    if product is None or not og_type or og_type.group(1).strip().lower() != "product":
        raise NotFoundError("no es una ficha de producto de Buscalibre")
    if str(product.get("sku") or product.get("identifier") or "") != ref.external_id:
        raise FetchError(f"la ficha es de otro producto ({product.get('sku')!r})")
    options = []
    for m in _OPTION_RE.finditer(raw):
        try:
            payload = json.loads(htmllib.unescape(m.group(1)))
        except ValueError as exc:
            raise FetchError("una opción de compra de Buscalibre no trae JSON válido") from exc
        if not isinstance(payload, dict):
            raise FetchError("opción de compra de Buscalibre inesperada")
        if str(payload.get("id_producto")) != ref.external_id:
            continue  # opción de otro producto (no debería pasar en #opciones)
        options.append(payload)
    return product, options


def _ld_path(product: dict, ref: ProductRef) -> str | None:
    m = _URL_RE.match(str(product.get("url") or ""))
    if not m or str(int(m.group(3))) != ref.external_id:
        return None
    return f"/{m.group(1).lower()}/{m.group(2)}/p/{ref.external_id}"


def _ld_has_price(product: dict) -> bool:
    offers = product.get("offers")
    offers = offers if isinstance(offers, list) else [offers]
    return any(isinstance(o, dict) and to_minor(o.get("price"), "CLP") for o in offers)


def _flag(option: dict, key: str) -> bool:
    """`usado` / `importacion` vienen como "0"/"1" (o 0/1); otra cosa es un HTML cambiado."""
    value = option.get(key)
    if str(value) not in {"0", "1"} or isinstance(value, bool):
        raise FetchError(f"opción de compra con {key} inesperado: {value!r}")
    return str(value) == "1"


def _best(options: list[dict], mode: str) -> tuple[int, int | None] | None:
    """(precio, precio tachado) de la opción más barata que cuenta el modo."""
    found = []
    for o in options:
        used, imported = _flag(o, "usado"), _flag(o, "importacion")
        if mode != "todos" and used:
            continue
        price = to_minor(o.get("precio_moneda_raw"), "CLP")
        if not price or price <= 0:
            # Un precio en cero es un dato roto, no una oferta (ni un agotado).
            raise FetchError(f"opción de compra sin precio: {o.get('precio_moneda_raw')!r}")
        crossed = to_minor(o.get("precio_tachado_moneda_raw"), "CLP")
        # El tachado de un importado es una fórmula (~2× el precio), no un precio real.
        if imported or not o.get("mostrar_descuento") or not crossed or crossed <= price:
            crossed = None
        found.append((price, crossed))
    return min(found, key=lambda f: f[0]) if found else None
