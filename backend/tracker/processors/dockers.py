"""Procesador de Dockers (dockers.cl, ropa; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class DockersProcessor(ShopifyApparelProcessor):
    name = "dockers"
    label = "Dockers"
    host = "dockers.cl"
    canonical_host = "www.dockers.cl"
    home_url = "https://www.dockers.cl/"
    example_url = "https://www.dockers.cl/products/reversible-leather-belt-a"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
