"""Procesador de Head Chile (head.cl, Magento 2; mismo grupo y plataforma que Sparta).

Todo lo común está en `MagentoProcessor`. Mismo tema que Speedo: el stock es
`<p class="availability in-stock|out-of-stock">`. Las raquetas y palas eligen el grip
(`talla_raquetas`) con el selector clásico de Magento: la configuración viene en
`spConfig` (no `jsonConfig`), y un grip agotado queda con `products: []`.
"""

from tracker.processors.magento import MagentoProcessor


class HeadProcessor(MagentoProcessor):
    name = "head"
    label = "Head"
    host = "head.cl"
    stock_marker = "availability"
    home_url = "https://head.cl/"
    example_url = (
        "https://head.cl/raqueta-tenis-head-speed-mp-legend-2025-negra-104000000023207621.html"
    )
    variants_title = "¿Qué talla o grip seguir?"
    notes = (
        'Tenis y pádel. Precio de la ficha; el "precio habitual" tachado queda como precio '
        "antes. Sin elegir talla (o grip) se sigue el precio más bajo entre las que tienen "
        "stock; la tienda no muestra las agotadas."
    )
