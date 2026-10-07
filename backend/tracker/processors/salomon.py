"""Procesador de Salomon (salomon.cl, calzado y ropa outdoor; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class SalomonProcessor(ShopifyApparelProcessor):
    name = "salomon"
    label = "Salomon"
    host = "salomon.cl"
    canonical_host = "salomon.cl"
    home_url = "https://salomon.cl/"
    example_url = "https://salomon.cl/products/xt-6-protective"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
