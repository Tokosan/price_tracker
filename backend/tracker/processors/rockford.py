"""Procesador de Rockford (rkflife.com, ropa y calzado; también vende otras marcas del grupo; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class RockfordProcessor(ShopifyApparelProcessor):
    name = "rockford"
    label = "Rockford"
    host = "rkflife.com"
    canonical_host = "www.rkflife.com"
    home_url = "https://www.rkflife.com/"
    example_url = "https://www.rkflife.com/products/blusa-manga-larga-mujer-bls-petunia-aw26-rockford-rk210021679-po4"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
