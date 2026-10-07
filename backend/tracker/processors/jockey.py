"""Procesador de Jockey (jockey.cl, ropa interior; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class JockeyProcessor(ShopifyApparelProcessor):
    name = "jockey"
    label = "Jockey"
    host = "jockey.cl"
    canonical_host = "jockey.cl"
    home_url = "https://jockey.cl/"
    example_url = "https://jockey.cl/products/jockey-boxer-hombre-algodon-tallas-grandes-unitario"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
