"""Procesador de Aldo Chile (aldo.cl/aldo-cl), vía la API de la plataforma Falabella.

La tienda corre sobre la plataforma de Falabella (`static.falabella.io`) y su API de
browse es la misma, con `site=aldo-cl`. Fichas `/aldo-cl/product/<pid>/<slug>[/<sku>]`:
cada talla es una variante con su SKU, su precio y su stock.
"""

from tracker.processors.falabella_platform import FalabellaPlatformProcessor


class AldoProcessor(FalabellaPlatformProcessor):
    name = "aldo"
    label = "Aldo"
    hosts = ("www.aldo.cl", "aldo.cl")
    canonical_host = "www.aldo.cl"
    site = "aldo-cl"
    path_kind = "product"
    home_url = "https://www.aldo.cl/aldo-cl"
    example_url = (
        "https://www.aldo.cl/aldo-cl/product/15933076/"
        "Finespec-Zapatilla-Urbana-Hombre-Negra-Aldo/15933077"
    )
    variants_title = "¿Qué talla seguir?"
    variants_hint = "Cada talla tiene su propio precio y stock. Marca las que quieras."
    notes = (
        'Precio internet (o el de evento, si hay). El precio "antes" es el normal tachado. '
        "Cada talla se sigue por separado. Si el link no trae SKU, se fija la talla que "
        "muestra la ficha; como link extra de un producto ya seguido, se sigue la talla por "
        "defecto, que puede cambiar."
    )
