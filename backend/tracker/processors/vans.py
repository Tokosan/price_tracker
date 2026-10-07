"""Procesador de Vans (vans.cl, zapatillas y ropa; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class VansProcessor(ShopifyApparelProcessor):
    name = "vans"
    label = "Vans"
    host = "vans.cl"
    canonical_host = "www.vans.cl"
    home_url = "https://www.vans.cl/"
    example_url = (
        "https://www.vans.cl/products/zapatilla-nino-knu-skool-elastic-la-vans-vn000d0kfsb-wh5"
    )
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
