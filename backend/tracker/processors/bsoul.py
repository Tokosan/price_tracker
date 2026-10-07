"""Procesador de B-Soul (bsoul.com, ropa deportiva; también vende Brooks; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class BSoulProcessor(ShopifyApparelProcessor):
    name = "bsoul"
    label = "B-Soul"
    host = "bsoul.com"
    canonical_host = "www.bsoul.com"
    home_url = "https://www.bsoul.com/"
    example_url = (
        "https://www.bsoul.com/products/polera-m-c-mujer-t-shirt-anto-aloe-bsoul-bs210021859-n11"
    )
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado. Casi todo el catálogo trae un precio tachado, que se guarda como precio "
        "«antes»."
    )
