"""Procesador de Piedra Bruja (piedrabruja.cl, juegos de mesa, TCG y miniaturas; Shopify).

Todo lo común está en `ShopifyProcessor`. Casi todos los productos tienen una sola
variante; los cursos y talleres traen una por fecha. Las preventas se venden como un
producto en stock. Los torneos gratuitos tienen precio 0: con cupo se rechazan al agregarlos
(no hay precio que seguir).
"""

from datetime import timedelta

from tracker.processors.shopify import ShopifyProcessor


class PiedraBrujaProcessor(ShopifyProcessor):
    name = "piedrabruja"
    label = "Piedra Bruja"
    host = "piedrabruja.cl"
    canonical_host = "piedrabruja.cl"
    check_interval = timedelta(hours=12)
    home_url = "https://piedrabruja.cl/"
    example_url = "https://piedrabruja.cl/products/miniaturas-para-la-bomba-de-piedrabruja"
    supports_variants = True
    variants_hint = "Cada variante (p. ej. la fecha de un curso) se sigue por separado."
    notes = (
        "Precio de la ficha (el mismo con cualquier medio de pago). Las preventas cuentan "
        "como disponibles mientras se puedan comprar. Los productos con variantes (p. ej. "
        "las fechas de un curso) se eligen al agregarlos y cada una se sigue por separado. "
        "Los productos gratuitos (torneos) no se pueden seguir."
    )
