"""Procesador de Opaline (opaline.cl, ropa infantil de Colgram, plataforma VTEX, cuenta
`opalinecl`).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class OpalineProcessor(VtexApparelProcessor):
    name = "opaline"
    label = "Opaline"
    host = "www.opaline.cl"
    account = "opalinecl"
    home_url = "https://www.opaline.cl/"
    example_url = "https://www.opaline.cl/conjunto-3-piezas-beige-bebe-unisex/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
