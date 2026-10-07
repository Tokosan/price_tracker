"""Procesador de Wrangler (wrangler.cl, jeans y ropa; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class WranglerProcessor(ShopifyApparelProcessor):
    name = "wrangler"
    label = "Wrangler"
    host = "wrangler.cl"
    canonical_host = "wrangler.cl"
    home_url = "https://wrangler.cl/"
    example_url = (
        "https://wrangler.cl/products/camisa-hombre-manga-larga-lino-1-bolsillo-slim-tapered-light"
    )
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
