"""Procesador de Colloky (colloky.cl, ropa y calzado infantil de Colgram, plataforma VTEX,
cuenta `colgramcl`).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class CollokyProcessor(VtexApparelProcessor):
    name = "colloky"
    label = "Colloky"
    host = "www.colloky.cl"
    account = "colgramcl"
    home_url = "https://www.colloky.cl/"
    example_url = "https://www.colloky.cl/zapatilla-deportiva-nina-azul-21-27/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
