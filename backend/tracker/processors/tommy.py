"""Procesador de Tommy Hilfiger Chile (cl.tommy.com, plataforma VTEX, cuenta `tommychile`).

El sitio no usa `www.` (la base acepta el host tal cual y con `www.`).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class TommyProcessor(VtexApparelProcessor):
    name = "tommy"
    label = "Tommy Hilfiger"
    host = "cl.tommy.com"
    account = "tommychile"
    home_url = "https://cl.tommy.com/"
    example_url = "https://cl.tommy.com/zapatillas-acabado-granulado-fm0fm05367dw5/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
