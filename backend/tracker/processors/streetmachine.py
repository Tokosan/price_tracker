"""Procesador de Street Machine (streetmachine.cl, multimarca de ropa y calzado urbano; Shopify).

Todo lo común está en `ShopifyProcessor` y `ShopifyApparelProcessor`.
"""

from tracker.processors.shopify import ShopifyApparelProcessor


class StreetMachineProcessor(ShopifyApparelProcessor):
    name = "streetmachine"
    label = "Street Machine"
    host = "streetmachine.cl"
    canonical_host = "www.streetmachine.cl"
    home_url = "https://www.streetmachine.cl/"
    example_url = "https://www.streetmachine.cl/products/polera-reef-pv2719blancl-rfmpov2719bl"
    notes = (
        "Precio de la tienda online. Cada talla o color se elige al agregar y se sigue por "
        "separado."
    )
