"""Procesador de Kayser (kaysershop.com, ropa interior y lencería; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class KayserProcessor(ShopifyApparelProcessor):
    name = "kayser"
    label = "Kayser"
    host = "kaysershop.com"
    canonical_host = "kaysershop.com"
    home_url = "https://kaysershop.com/"
    example_url = "https://kaysershop.com/products/calzon-pantaletas-p315-7095-rosado"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
