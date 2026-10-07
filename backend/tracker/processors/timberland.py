"""Procesador de Timberland Chile (www.timberland.cl), sobre la plataforma Fenicio.

Todo lo común está en `FenicioProcessor`. Cada color es su propia URL
(`/catalogo/<slug>_<codProducto>_<codColor>`) y las tallas se siguen dentro de la ficha.
"""

from tracker.processors.fenicio import FenicioProcessor


class TimberlandProcessor(FenicioProcessor):
    name = "timberland"
    label = "Timberland"
    hosts = ("www.timberland.cl", "timberland.cl")
    canonical_host = "www.timberland.cl"
    home_url = "https://www.timberland.cl/"
    example_url = "https://www.timberland.cl/catalogo/zapatilla-mid-lace-up-hombre-em5_TB0A424R_EM5"
    notes = (
        'Precio de venta de la ficha; el "antes" es el precio tachado. Cada color es un link '
        "distinto. Puedes seguir cualquier talla (disponible si queda alguna) o una talla "
        "puntual; todas las tallas de un color tienen el mismo precio."
    )
