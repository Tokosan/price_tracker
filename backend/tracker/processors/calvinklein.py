"""Procesador de Calvin Klein Chile (calvinklein.cl, plataforma VTEX, cuenta `calvinchile`).

Lo opera el mismo vendedor que Tommy Hilfiger ("AMERICAN SPORTSWEAR, S.A.").
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class CalvinKleinProcessor(VtexApparelProcessor):
    name = "calvinklein"
    label = "Calvin Klein"
    host = "www.calvinklein.cl"
    account = "calvinchile"
    home_url = "https://www.calvinklein.cl/"
    example_url = "https://www.calvinklein.cl/pack-3-boxers-ajustados-intense-power-nb3608927/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
