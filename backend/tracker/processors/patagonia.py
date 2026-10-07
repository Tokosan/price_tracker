"""Procesador de Patagonia (cl.patagonia.com, ropa outdoor, también usada (Worn Wear); Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class PatagoniaProcessor(ShopifyApparelProcessor):
    name = "patagonia"
    label = "Patagonia"
    host = "cl.patagonia.com"
    canonical_host = "cl.patagonia.com"
    home_url = "https://cl.patagonia.com/"
    example_url = "https://cl.patagonia.com/products/65485-polar-de-nina-los-gatos-poleron-usado"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
