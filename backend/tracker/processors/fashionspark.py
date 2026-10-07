"""Procesador de Fashion's Park (fashionspark.com, ropa; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class FashionsParkProcessor(ShopifyApparelProcessor):
    name = "fashionspark"
    label = "Fashion's Park"
    host = "fashionspark.com"
    canonical_host = "fashionspark.com"
    home_url = "https://fashionspark.com/"
    example_url = "https://fashionspark.com/products/poleron-nina-stitch-fucsia-201088601"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
