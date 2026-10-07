"""Procesador de Lippi (lippioutdoor.com, ropa y equipo outdoor; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class LippiProcessor(ShopifyApparelProcessor):
    name = "lippi"
    label = "Lippi"
    host = "lippioutdoor.com"
    canonical_host = "www.lippioutdoor.com"
    home_url = "https://www.lippioutdoor.com/"
    example_url = "https://www.lippioutdoor.com/products/polar-mujer-ruil-negro-haka-honu"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
