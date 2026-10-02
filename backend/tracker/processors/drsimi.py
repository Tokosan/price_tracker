"""Procesador de Farmacias del Dr. Simi (drsimi.cl, plataforma VTEX).

Un solo vendedor y un item por producto. `AvailableQuantity` viene en 99999 (o 100, 10…)
con stock y en 0 con `IsAvailable: false` en un agotado, que conserva su precio.

La tienda no usa `ListPrice` (igual a `Price` en todo el catálogo al 2026-10-02). La base
lee también `PriceWithoutDiscount` como precio "antes", suponiendo que una promoción del
catálogo dejaría ahí el precio previo; es una suposición sin un caso real observado (hoy
vale lo mismo que `Price` en todos los productos).
Las promociones por cantidad ("Club de amigos - 33 % al llevar 3", "3x2") vienen como
`Teasers`, no cambian `Price` y se ignoran.
"""

from tracker.processors.vtex import VtexProcessor


class DrSimiProcessor(VtexProcessor):
    name = "drsimi"
    label = "Dr. Simi"
    host = "www.drsimi.cl"
    account = "farmaciasdeldrsimicl"
    home_url = "https://www.drsimi.cl/"
    example_url = "https://www.drsimi.cl/paracetamol-500-mg-16-comprimidos/p"
    notes = (
        "Precio de la venta online. Las promociones por cantidad (Club de amigos, 3x2) "
        "no se guardan. Un agotado conserva su precio."
    )
