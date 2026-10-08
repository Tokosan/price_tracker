"""Procesador de Speedo Chile (speedo.cl, Magento 2; mismo grupo y plataforma que Sparta).

Todo lo común está en `MagentoProcessor`. Otro tema que Sparta: el stock es
`<p class="availability in-stock|out-of-stock">` ("En stock" / "Sin stock") y las tallas
vendibles vienen en el `jsonConfig` del swatch-renderer.
"""

from tracker.processors.magento import MagentoProcessor


class SpeedoProcessor(MagentoProcessor):
    name = "speedo"
    label = "Speedo"
    host = "speedo.cl"
    stock_marker = "availability"
    home_url = "https://speedo.cl/"
    example_url = (
        "https://speedo.cl/traje-de-bano-natacion-mujer-speedo-training-comfort-v-back-rosado-"
        "24208-a00030000506.html"
    )
    notes = (
        'Natación. Precio de la ficha; el "precio habitual" tachado queda como precio antes. '
        "Cada color tiene su propio link. Sin elegir talla se sigue el precio más bajo entre "
        "las tallas con stock; la tienda no muestra las tallas agotadas."
    )
