"""Procesador de Keds Chile (keds.cl, plataforma VTEX, cuenta `kedscl`).

El precio normal (`ListPrice`) es una fórmula: en todo el catálogo con stock vale 2,5 veces
el precio (un "60 % off" permanente al 2026-10-07), así que no se guarda como precio
"antes" (como los importados de Buscalibre).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class KedsProcessor(VtexApparelProcessor):
    name = "keds"
    label = "Keds"
    host = "www.keds.cl"
    account = "kedscl"
    supports_list_price = False
    home_url = "https://www.keds.cl/"
    example_url = "https://www.keds.cl/zapatilla-mujer-kickstart-seasonal-s-keds-wf54682-boh/p"
    notes = (
        'Precio online de cada talla. El precio "antes" de la tienda no se guarda: es '
        "siempre 2,5 veces el precio (un 60 % de descuento permanente). Cada talla se sigue "
        "por separado."
    )
