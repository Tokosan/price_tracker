"""Procesador de Levi's Chile (levi.cl, plataforma VTEX, cuenta `leviscl`).

Los jeans tienen dos atributos por item: cintura y largo (`Cintura`, `Largo`).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class LevisProcessor(VtexApparelProcessor):
    name = "levis"
    label = "Levi's"
    host = "www.levi.cl"
    account = "leviscl"
    home_url = "https://www.levi.cl/"
    example_url = "https://www.levi.cl/jeans-hombre-levis-505-regular-00505-3437/p"
    notes = (
        "Precio online de cada talla (cintura y largo en los jeans); el precio normal "
        'tachado se guarda como precio "antes". Cada talla se sigue por separado.'
    )
