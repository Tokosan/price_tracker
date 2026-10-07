"""Procesador de Gotta (gotta.cl, calzado de mujer; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class GottaProcessor(ShopifyApparelProcessor):
    name = "gotta"
    label = "Gotta"
    host = "gotta.cl"
    canonical_host = "gotta.cl"
    home_url = "https://gotta.cl/"
    example_url = "https://gotta.cl/products/sandalia-plataforma-negro-mujer-13221"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
