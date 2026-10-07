"""Procesador de Hush Puppies (hushpuppies.cl, calzado y accesorios; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class HushPuppiesProcessor(ShopifyApparelProcessor):
    name = "hushpuppies"
    label = "Hush Puppies"
    host = "hushpuppies.cl"
    canonical_host = "www.hushpuppies.cl"
    home_url = "https://www.hushpuppies.cl/"
    example_url = (
        "https://www.hushpuppies.cl/products/mocasin-hombre-kent-hush-puppies-hp10201162689-551"
    )
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
