"""Procesador de Under Armour (underarmour.cl, ropa y calzado deportivo; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class UnderArmourProcessor(ShopifyApparelProcessor):
    name = "underarmour"
    label = "Under Armour"
    host = "underarmour.cl"
    canonical_host = "www.underarmour.cl"
    home_url = "https://www.underarmour.cl/"
    example_url = "https://www.underarmour.cl/products/zapatilla-aurora-3-mujer-blanco"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
