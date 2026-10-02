"""Procesador de Ecofarmacias (www.ecofarmacias.cl, WordPress + WooCommerce).

Todo lo común está en `WooCommerceProcessor` (Store API `wc/store/v1`). Las ofertas suelen
ser una publicación aparte del mismo producto, con el slug terminado en `-descuento` y pocas
unidades: se sigue la ficha que se pegó, no se buscan sus hermanas.
"""

from tracker.processors.woocommerce import WooCommerceProcessor


class EcofarmaciasProcessor(WooCommerceProcessor):
    name = "ecofarmacias"
    label = "Ecofarmacias"
    host = "ecofarmacias.cl"
    canonical_host = "www.ecofarmacias.cl"
    home_url = "https://www.ecofarmacias.cl/"
    example_url = "https://www.ecofarmacias.cl/producto/ensure-advance-chocolate-850-g/"
    supports_variants = True
    variants_hint = "Cada variante (color, talla…) se sigue por separado. Marca las que quieras."
    notes = (
        "Las ofertas suelen ser una ficha aparte (slug terminado en «-descuento») con pocas "
        "unidades: sigue la ficha que te interese. En productos con variantes (color, talla) "
        "cada una se elige al agregarlo y se sigue por separado. Un producto sin precio y sin "
        "stock cuenta como agotado."
    )
