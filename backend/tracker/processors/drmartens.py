"""Procesador de Dr. Martens (drmartens.cl, calzado; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class DrMartensProcessor(ShopifyApparelProcessor):
    name = "drmartens"
    label = "Dr. Martens"
    host = "drmartens.cl"
    canonical_host = "drmartens.cl"
    home_url = "https://drmartens.cl/"
    example_url = "https://drmartens.cl/products/unisex-originals-boots-arcadia-1460"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
