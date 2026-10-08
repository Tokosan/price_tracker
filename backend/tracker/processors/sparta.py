"""Procesador de Sparta (sparta.cl, Magento 2 / Adobe Commerce detrás de Fastly).

Todo lo común está en `MagentoProcessor` (ficha HTML; el GraphQL oculta los agotados). El
stock es el `<div class="stock available|unavailable">` de `product-info-stock-sku`, y las
tallas vendibles vienen en el `jsonConfig` del swatch-renderer (`ropa_talla`,
`Talla Nacional`, `bici_talla`…). Hay SKUs con punto (`01501012C008.7002207`).
"""

from tracker.processors.magento import MagentoProcessor


class SpartaProcessor(MagentoProcessor):
    name = "sparta"
    label = "Sparta"
    host = "sparta.cl"
    stock_marker = "stock_div"
    home_url = "https://sparta.cl/"
    example_url = "https://sparta.cl/zapatillas-urbanas-mujer-montagne-radiance-blanco-68400radiancemwh01.html"
    notes = (
        'Artículos deportivos. Precio de la ficha; el "precio habitual" tachado queda como '
        "precio antes. Cada color tiene su propio link. Sin elegir talla se sigue el precio "
        "más bajo entre las tallas con stock; Sparta no muestra las tallas agotadas."
    )
