"""Procesador de Marathon (marathon.cl, Salesforce Commerce Cloud; tienda deportiva
multimarca).

Se lee `Product-Variation` (ver `SFCCVariationProcessor`). Sin el parámetro `imageSize`
(que agrega el front al elegir talla) responde HTTP 500 a cualquier pedido.

Cada talla tiene su propio pid y su propia ficha:
`/<marca>/<slug>/<modelo-color>/<pid>.html` (`/<pid>.html` redirige a ella). El link que
se pega es siempre el de una talla, así que no hay selección en `variant_id`. Los otros
colores son otros modelos, con sus propios links.

El JSON no trae los pid de las otras tallas: solo los valores para pedirlas al maestro
(`M044…`, con espacios a veces) con `dwvar_`. Por eso el selector pide una vez cada talla
(solo al agregar, de a una) y lee su `variantURL`.
"""

import asyncio
import logging
import re
from urllib.parse import unquote_plus, urlsplit

from tracker.processors.base import FetchError, Inspection, ProductRef, Variant
from tracker.processors.sfcc import (
    SFCCVariationProcessor,
    attr_name,
    dwvar_pid,
    selected_values,
    variation_attributes,
)

log = logging.getLogger(__name__)

# Tope de tallas que se piden al abrir el selector (las zapatillas traen ~10).
MAX_SIZES = 20
SIZE_PAUSE_S = 0.3


class MarathonProcessor(SFCCVariationProcessor):
    name = "marathon"
    label = "Marathon"
    hosts = frozenset({"www.marathon.cl", "marathon.cl"})
    canonical_host = "www.marathon.cl"
    site_id = "MarathonChile"
    locale = "es_CL"
    path_re = re.compile(r"^/(?:[^/]+/)*(?P<pid>\d{8,})\.html$", re.I)
    uses_dwvar = False
    variation_extra = (("imageSize", "hi-res"),)
    title_with_selection = True
    home_url = "https://www.marathon.cl/"
    example_url = (
        "https://www.marathon.cl/marcas/puma/puma-zapatillas-magmax-nitro-2/312126-03/"
        "11140411010.html"
    )
    variants_title = "¿Qué talla seguir?"
    variants_hint = "Cada talla se sigue por separado. Marca las que quieras."
    notes = (
        "Cada talla tiene su propio link: el que pegas es el de la talla elegida (las otras "
        "aparecen en el selector). Los descuentos con tarjetas de bancos no se guardan."
    )

    def canonical_path(self, m: re.Match) -> str:
        return f"/{m.group('pid')}.html"

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        return []  # hace falta pedir cada talla: ver `inspect`

    async def inspect(self, ref: ProductRef) -> Inspection:
        raw = await self.fetch_raw(ref)
        return Inspection(self.parse(raw, ref), await self.size_variants(raw, ref))

    async def list_variants(self, ref: ProductRef) -> list[Variant]:
        return await self.size_variants(await self.fetch_raw(ref), ref)

    async def size_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las tallas del mismo color, cada una con su link (una petición por talla)."""
        product = self.product(raw)
        attrs = variation_attributes(product)
        size = next((a for a in attrs if a["id"] == "size"), None)
        current = selected_values(product)
        master = _master(product)
        if not size or len(size["values"]) < 2 or not master:
            return []
        if set(current) != {a["id"] for a in attrs}:
            return []
        name = attr_name(size)
        out = [
            Variant(
                ref.canonical_url,
                _label(name, _shown(size, current["size"]), not self.is_available(product)),
                ref.external_id,
                selected=True,
            )
        ]
        real = [v for v in size["values"] if _is_real_size(v)]
        for value in real[:MAX_SIZES]:
            if value["id"] == current["size"]:
                continue
            await asyncio.sleep(SIZE_PAUSE_S)
            combo = {**current, "size": value["id"]}
            params = {
                "pid": master,
                **{f"dwvar_{dwvar_pid(master)}_{a}": v for a, v in combo.items()},
                **dict(self.variation_extra),
            }
            try:
                other = self.product(
                    await self.http_get(self.controller_url("Product-Variation"), params=params)
                )
            except FetchError as exc:
                log.warning(
                    "Marathon: no se pudo leer la talla %s de %s: %s", value["id"], master, exc
                )
                continue
            sku = str(other.get("id") or "")
            if not re.fullmatch(r"\d{8,}", sku) or selected_values(other) != combo:
                continue
            out.append(
                Variant(
                    f"https://{self.canonical_host}/{sku}.html",
                    _label(name, _shown(size, value["id"]), not self.is_available(other)),
                    sku,
                )
            )
        return out if len(out) > 1 else []


def _master(product: dict) -> str | None:
    """Pid del maestro, desde `selectedProductUrl` (`/…/M0441115881-1010.html?…`)."""
    path = unquote_plus(urlsplit(product.get("selectedProductUrl") or "").path)
    stem = path.rsplit("/", 1)[-1]
    return stem.removesuffix(".html") if stem.endswith(".html") and len(stem) > 5 else None


def _is_real_size(value: dict) -> bool:
    """El maestro lista todas las tallas de la curva (1 a 10.5 en una zapatilla), también las
    que el modelo no tiene: esas vienen sin `eanValue` y no aparecen en la ficha."""
    return bool(value.get("id")) and ("eanValue" not in value or bool(value.get("eanValue")))


def _shown(attr: dict, value_id: str) -> str:
    value = next((v for v in attr["values"] if v.get("id") == value_id), {})
    return value.get("displayValue") or value_id


def _label(name: str, shown: str, unavailable: bool) -> str:
    return f"{name}: {shown} (no disponible)" if unavailable else f"{name}: {shown}"
