"""Procesador de Reebok Chile (reebok.cl, plataforma VTEX, cuenta `reebokcl`)."""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class ReebokProcessor(VtexApparelProcessor):
    name = "reebok"
    label = "Reebok"
    host = "www.reebok.cl"
    account = "reebokcl"
    home_url = "https://www.reebok.cl/"
    example_url = (
        "https://www.reebok.cl/calzas-running-high-rise-full-length-tights-mujer-100241933/p"
    )
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Las tallas se eligen al agregar y cada una se sigue por separado.'
    )
