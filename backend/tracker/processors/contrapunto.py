"""Procesador de Contrapunto (contrapunto.cl, librería; Shopify).

Todo lo común está en `ShopifyProcessor`. Los libros tienen una sola variante, así que no
hay selector. Casi todo el catálogo tiene un descuento permanente (el precio tachado es el
de lista), y las preventas se venden como un producto en stock.
"""

from datetime import timedelta

from tracker.processors.shopify import ShopifyProcessor


class ContrapuntoProcessor(ShopifyProcessor):
    name = "contrapunto"
    label = "Contrapunto"
    host = "contrapunto.cl"
    canonical_host = "contrapunto.cl"
    check_interval = timedelta(hours=12)
    home_url = "https://contrapunto.cl/"
    example_url = "https://contrapunto.cl/products/verity"
    notes = (
        "Precio de la ficha (el mismo con cualquier medio de pago); casi todo el catálogo "
        "tiene un descuento permanente sobre el precio de lista, que se guarda como precio "
        "«antes». Las preventas cuentan como disponibles mientras se puedan comprar."
    )
