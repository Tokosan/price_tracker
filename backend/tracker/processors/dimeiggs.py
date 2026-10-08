"""Procesador de Dimeiggs (www.dimeiggs.cl, librería y oficina; plataforma VTEX).

Todo lo común está en `VtexProcessor` (cuenta `dimeiggsschl`). Un vendedor y un item por
producto. Casi todo el catálogo trae `ListPrice` > `Price`: es el descuento que la ficha
muestra (`discountHighlights`), así que se guarda como precio "antes". Un agotado
conserva su precio (`AvailableQuantity: 0`) y sigue listado por slug.
"""

from tracker.processors.vtex import VtexProcessor


class DimeiggsProcessor(VtexProcessor):
    name = "dimeiggs"
    label = "Dimeiggs"
    host = "www.dimeiggs.cl"
    account = "dimeiggsschl"
    home_url = "https://www.dimeiggs.cl/"
    example_url = "https://www.dimeiggs.cl/forro-para-cuaderno-college-rosado-dimeiggs/p"
    notes = (
        "Librería y artículos de oficina. Precio de la venta online; el precio normal queda "
        'como precio "antes". Un agotado conserva su precio.'
    )
