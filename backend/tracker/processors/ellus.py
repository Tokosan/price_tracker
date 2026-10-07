"""Procesador de Ellus Chile (ellus.cl, plataforma VTEX, cuenta `elluscl`).

Los items combinan talla y color, y muchos slugs usan guiones bajos
(`jeans_hombre_straight_tiro_alto`). Las promociones por cantidad ("2x1 Boxers")
vienen como `Teasers`, no cambian `Price` y se ignoran.
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class EllusProcessor(VtexApparelProcessor):
    name = "ellus"
    label = "Ellus"
    host = "www.ellus.cl"
    account = "elluscl"
    home_url = "https://www.ellus.cl/"
    example_url = "https://www.ellus.cl/jeans_hombre_straight_tiro_alto/p"
    notes = (
        "Precio online de cada talla y color; el precio normal tachado se guarda como "
        'precio "antes". Las promociones por cantidad (2x1) no se guardan.'
    )
