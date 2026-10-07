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

La lectura y el selector son los de `SFCCVariationProcessor`.
"""

from tracker.processors.sfcc import SFCCVariationProcessor, decode_selection


class HitesProcessor(SFCCVariationProcessor):
    name = "hites"
    label = "Hites"
    hosts = frozenset({"www.hites.com", "hites.com"})
    canonical_host = "www.hites.com"
    site_id = "HITES"
    home_url = "https://www.hites.com/"
    example_url = "https://www.hites.com/juego-nintendo-switch-2-mario-kart-world-957877001.html"
    variants_hint = (
        "Cada combinación se sigue por separado. Se muestran los otros colores en la misma "
        "talla y las otras tallas del mismo color. Marca las que quieras."
    )
    notes = (
        "Precio para todo medio de pago; el precio con Tarjeta Hites no se guarda. En ropa "
        "y calzado, pega el link después de elegir color y talla (o elígelos en el selector)."
    )

    def is_available(self, product: dict) -> bool:
        status = (product.get("availability") or {}).get("status")
        return product.get("available") is True and status == "IN_STOCK"

    def variant_label(self, external_id: str, variant_id: str) -> str:
        return ", ".join(decode_selection(variant_id).values())
