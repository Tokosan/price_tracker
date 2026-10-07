"""Procesador de Ferouch (ferouch.cl, plataforma VTEX, cuenta `ferouchcl`).

Los items combinan talla y color; cada color suele tener su propia ficha.
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class FerouchProcessor(VtexApparelProcessor):
    name = "ferouch"
    label = "Ferouch"
    host = "www.ferouch.cl"
    account = "ferouchcl"
    home_url = "https://www.ferouch.cl/"
    example_url = "https://www.ferouch.cl/polo-pique-lt-pink/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
