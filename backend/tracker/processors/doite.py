"""Procesador de Doite (doite.cl, ropa y equipo outdoor; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class DoiteProcessor(ShopifyApparelProcessor):
    name = "doite"
    label = "Doite"
    host = "doite.cl"
    canonical_host = "www.doite.cl"
    home_url = "https://www.doite.cl/"
    example_url = "https://www.doite.cl/products/polera-manga-corta-mountain-logo-hombre-doite"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
