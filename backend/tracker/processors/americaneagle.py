"""Procesador de American Eagle Chile (ae.cl, plataforma VTEX, cuenta `americaneaglecl`)."""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class AmericanEagleProcessor(VtexApparelProcessor):
    name = "americaneagle"
    label = "American Eagle"
    host = "www.ae.cl"
    account = "americaneaglecl"
    home_url = "https://www.ae.cl/"
    example_url = "https://www.ae.cl/polera-ae-playera-ligera-lisa-11641539001/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
