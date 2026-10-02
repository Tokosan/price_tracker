"""Procesador de Hites (hites.com, Salesforce Commerce Cloud).

Se lee el controlador `Product-Variation` (JSON con precio, stock y variaciones) en vez
de la ficha HTML, que pesa ~2 MB. Precios en `product.price`: `sales` es el precio para
todo medio de pago, `list` el normal tachado y `hites`/`bestPrice` el de la Tarjeta
Hites, que no se usa.

La URL de una ficha es `/<slug>-<pid>.html`. El pid puede ser el de una variante
(`…-954699016.html`) o el de un maestro con la variante elegida en la query
(`…-954699.html?dwvar_954699_color=NARANJA&dwvar_954699_Talla-Vestuario-Generica=TM`,
que es lo que deja el sitio en la barra al elegir color y talla): esa selección va en
`variant_id`. Con un maestro sin selección, la API responde la variante por defecto, y
con una combinación agotada responde el maestro con `available: false`.

Un pid inexistente da HTTP 500 en la API (y 404 en la ficha): se confirma con el HTML.
"""

import json
from urllib.parse import urlsplit

from tracker.processors.base import FetchError, NotFoundError, ProductRef, ScrapeResult, Variant
from tracker.processors.http import get_text
from tracker.processors.sfcc import (
    SFCCProcessor,
    decode_selection,
    dwvar_query,
    encode_selection,
    selected_values,
    variation_attributes,
)
from tracker.processors.util import to_minor


class HitesProcessor(SFCCProcessor):
    name = "hites"
    label = "Hites"
    hosts = frozenset({"www.hites.com", "hites.com"})
    canonical_host = "www.hites.com"
    site_id = "HITES"
    uses_dwvar = True
    fixture_ext = "json"
    home_url = "https://www.hites.com/"
    example_url = "https://www.hites.com/juego-nintendo-switch-2-mario-kart-world-957877001.html"
    supports_variants = True
    supports_list_price = True
    variants_title = "Color y talla"
    variants_hint = (
        "Cada combinación se sigue por separado. Se muestran los otros colores en la misma "
        "talla y las otras tallas del mismo color. Marca las que quieras."
    )
    notes = (
        "Precio para todo medio de pago; el precio con Tarjeta Hites no se guarda. En ropa "
        "y calzado, pega el link después de elegir color y talla (o elígelos en el selector)."
    )

    async def fetch_raw(self, ref: ProductRef) -> str:
        url = self.controller_url("Product-Variation")
        try:
            return await get_text(url, params=self.variation_params(ref))
        except NotFoundError:
            raise
        except FetchError:
            await get_text(ref.canonical_url)  # 404 → NotFoundError
            raise

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = _product(raw)
        self.check_selection(product, ref)
        prices = product.get("price") or {}
        sales = prices.get("sales") or {}
        currency = sales.get("currency") or "CLP"
        price = to_minor(sales.get("value"), currency)
        normal = to_minor((prices.get("list") or {}).get("value"), currency)
        status = (product.get("availability") or {}).get("status")
        large = (product.get("images") or {}).get("large") or []
        return ScrapeResult(
            title=(product.get("productName") or "").strip(),
            price=price,
            list_price=normal if normal and price is not None and normal > price else None,
            currency=currency,
            available=product.get("available") is True and status == "IN_STOCK",
            image_url=(large[0].get("url") if large and isinstance(large[0], dict) else None),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Combinaciones a un paso de la actual (sin pedir nada más a la tienda).

        `variationAttributes` trae, para cada atributo, sus valores y si se pueden elegir
        con el resto de la selección actual. Pedir cada color × talla serían muchas
        peticiones, así que se ofrece cambiar un atributo a la vez: los otros colores en
        la misma talla y las otras tallas del mismo color.
        """
        product = _product(raw)
        master = product.get("masterID") or (
            product.get("id") if product.get("productType") == "master" else None
        )
        attrs = variation_attributes(product)
        current = selected_values(product)
        path = self._master_path(product, ref, master)
        if not master or not path or not attrs or set(current) != {a["id"] for a in attrs}:
            return []
        names = {a["id"]: a.get("displayName") or a["id"] for a in attrs}
        shown = {
            (a["id"], v["id"]): v.get("displayValue") or v["id"]
            for a in attrs
            for v in a["values"]
            if v.get("id")
        }

        def label(combo: dict[str, str], unavailable: bool) -> str:
            text = ", ".join(f"{names[a]}: {shown.get((a, combo[a]), combo[a])}" for a in names)
            return f"{text} (no disponible)" if unavailable else text

        def url(combo: dict[str, str]) -> str:
            return f"https://{self.canonical_host}{path}?{dwvar_query(master, combo)}"

        # Un maestro sin selección sigue la variante por defecto, que puede cambiar: en
        # el selector se ofrece la combinación explícita.
        explicit = ref.external_id == master and not ref.variant_id
        here = encode_selection(current)
        out = [
            Variant(
                url(current) if explicit else ref.canonical_url,
                label(current, not self.parse(raw, ref).available),
                master if explicit else ref.external_id,
                here if explicit else ref.variant_id,
                selected=True,
            )
        ]
        seen = {here}
        for attr in attrs:
            if len(attr["values"]) < 2:
                continue
            for value in attr["values"]:
                if not value.get("id"):
                    continue
                combo = {**current, attr["id"]: value["id"]}
                key = encode_selection(combo)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Variant(
                        url=url(combo),
                        label=label(combo, value.get("selectable") is False),
                        external_id=master,
                        variant_id=key,
                    )
                )
        return out if len(out) > 1 else []

    def _master_path(self, product: dict, ref: ProductRef, master: str | None) -> str | None:
        """Ruta canónica del maestro (`/<slug>-<maestro>.html`)."""
        for url in (product.get("selectedProductUrl") or "", ref.canonical_url):
            m = self.path_re.match(urlsplit(url).path)
            if m and m.group("pid") == master:
                return self.canonical_path(m)
        return None

    def variant_label(self, external_id: str, variant_id: str) -> str:
        return ", ".join(decode_selection(variant_id).values())


def _product(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("Hites no devolvió JSON") from exc
    product = data.get("product") if isinstance(data, dict) else None
    if not isinstance(product, dict) or not product.get("id"):
        raise FetchError("la respuesta de Hites no trae el producto")
    return product
