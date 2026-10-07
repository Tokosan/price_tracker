"""Procesador de Bamers (bamers.cl, calzado; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class BamersProcessor(ShopifyApparelProcessor):
    name = "bamers"
    label = "Bamers"
    host = "bamers.cl"
    canonical_host = "www.bamers.cl"
    home_url = "https://www.bamers.cl/"
    example_url = "https://www.bamers.cl/products/zapatillas-nina-knit-flex-rosado-bmgsn081851"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
