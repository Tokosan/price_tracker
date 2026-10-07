"""Procesador de Columbia (columbiachile.cl, ropa y calzado outdoor; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class ColumbiaProcessor(ShopifyApparelProcessor):
    name = "columbia"
    label = "Columbia"
    host = "columbiachile.cl"
    canonical_host = "www.columbiachile.cl"
    home_url = "https://www.columbiachile.cl/"
    example_url = "https://www.columbiachile.cl/products/polera-m-l-hombre-terminal-tackle-ls-s-columbia-1388261-7zj"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
