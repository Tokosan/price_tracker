"""Procesador de Crocs (crocs.cl, calzado; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class CrocsProcessor(ShopifyApparelProcessor):
    name = "crocs"
    label = "Crocs"
    host = "crocs.cl"
    canonical_host = "www.crocs.cl"
    home_url = "https://www.crocs.cl/"
    example_url = (
        "https://www.crocs.cl/products/sueco-unisex-onepiece-tsunny-cls-crocs-212126-90h-349-1"
    )
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
