"""Procesador de Caffarena (caffarena.cl, plataforma VTEX, cuenta `caffarenacl`).

Los items combinan color y talla (pantys y medias de talla 1 a 4, o única).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class CaffarenaProcessor(VtexApparelProcessor):
    name = "caffarena"
    label = "Caffarena"
    host = "www.caffarena.cl"
    account = "caffarenacl"
    home_url = "https://www.caffarena.cl/"
    example_url = "https://www.caffarena.cl/media-pantalon-pret-a-porte-1046/p"
    notes = (
        "Precio online de cada color y talla; el precio normal tachado se guarda como "
        'precio "antes". Cada combinación se sigue por separado.'
    )
