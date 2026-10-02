"""Procesador de Gato Arcano (gatoarcano.cl, juegos de mesa; WordPress + WooCommerce).

Todo lo común está en `WooCommerceProcessor` (Store API `wc/store/v1`). Las fichas viven en
`/product/<slug>/` y el sitio no usa www (`www.` redirige con 301).

Las preventas son productos normales en la categoría `preventas` (con stock y comprables;
la fecha estimada va en la descripción): se siguen como cualquier otro. Los «próximamente»
no se pueden comprar (`is_purchasable: false`) y traen un precio de relleno ("0" o "1"):
cuentan como agotados sin precio, y al abrirse la venta vuelven a tener stock.
"""

from tracker.processors.woocommerce import WooCommerceProcessor


class GatoArcanoProcessor(WooCommerceProcessor):
    name = "gatoarcano"
    label = "Gato Arcano"
    host = "gatoarcano.cl"
    canonical_host = "gatoarcano.cl"
    product_base = "product"
    home_url = "https://gatoarcano.cl/"
    example_url = "https://gatoarcano.cl/product/lorenzo-el-magnfico-big-box/"
    supports_variants = True
    variants_hint = "Cada versión se sigue por separado. Marca las que quieras."
    notes = (
        "Las preventas se siguen como un producto más (con su precio de preventa). Los "
        "productos «próximamente» aún no se pueden comprar: cuentan como agotados hasta que "
        "abra la venta. Casi no hay productos con variantes; si los hay, cada una se sigue "
        "por separado."
    )
