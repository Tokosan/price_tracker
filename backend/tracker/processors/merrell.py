"""Procesador de Merrell (merrell.cl, calzado y ropa outdoor; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class MerrellProcessor(ShopifyApparelProcessor):
    name = "merrell"
    label = "Merrell"
    host = "merrell.cl"
    canonical_host = "www.merrell.cl"
    home_url = "https://www.merrell.cl/"
    example_url = "https://www.merrell.cl/products/camisa-m-l-hombre-m-franela-winter-merrell-mew23-msr001-28l"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
