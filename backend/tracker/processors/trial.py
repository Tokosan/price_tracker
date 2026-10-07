"""Procesador de Trial (trial.cl, plataforma VTEX, cuenta `trialcl`).

A diferencia de las otras tiendas de ropa, la rebaja viene en el precio de la tienda
(`PriceWithoutDiscount == Price`) y el precio normal solo en `ListPrice`.
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class TrialProcessor(VtexApparelProcessor):
    name = "trial"
    label = "Trial"
    host = "www.trial.cl"
    account = "trialcl"
    home_url = "https://www.trial.cl/"
    example_url = (
        "https://www.trial.cl/traje-hombre-formal-regular-executive-azul-marino-1550256981/p"
    )
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
