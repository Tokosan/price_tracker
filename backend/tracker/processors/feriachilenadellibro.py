"""Procesador de la Feria Chilena del Libro (feriachilenadellibro.cl, WordPress + WooCommerce).

Todo lo común está en `WooCommerceProcessor` (Store API `wc/store/v1`). Cada edición de un
libro (tapa dura, rústico, bolsillo) es una ficha aparte, con el ISBN al inicio del slug
(`/producto/9786313004485-el-extranjero/`): no hay productos variables. Las preventas son
productos simples con la etiqueta `pre-venta`, comprables y "en stock" como cualquier otro.
El precio de la ficha ("Precio Internet") es el mismo para todo medio de pago.
"""

from tracker.processors.woocommerce import WooCommerceProcessor


class FeriaChilenaDelLibroProcessor(WooCommerceProcessor):
    name = "feriachilenadellibro"
    label = "Feria Chilena del Libro"
    host = "feriachilenadellibro.cl"
    canonical_host = "feriachilenadellibro.cl"
    home_url = "https://feriachilenadellibro.cl/"
    example_url = "https://feriachilenadellibro.cl/producto/9786313004485-el-extranjero/"
    notes = (
        "Cada edición de un libro (tapa dura, rústico, bolsillo) es una ficha aparte: sigue "
        "la que te interese. Las preventas se siguen como cualquier libro, con stock."
    )
