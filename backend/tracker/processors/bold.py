"""Procesador de Bold (www.bold.cl), sobre SAP Commerce (API OCC del grupo Yaneken).

Todo lo común está en `SapCommerceProcessor`. Bold y Belsport son del mismo grupo y
comparten la API (`api-prd.ynk.cl`), cada una con su `baseSite`.
"""

from tracker.processors.sapcommerce import SapCommerceProcessor


class BoldProcessor(SapCommerceProcessor):
    name = "bold"
    label = "Bold"
    hosts = ("www.bold.cl", "bold.cl")
    canonical_host = "www.bold.cl"
    api_base = "https://api-prd.ynk.cl/rest/v2"
    base_site = "boldb2cstore"
    home_url = "https://www.bold.cl/"
    example_url = (
        "https://www.bold.cl/Categories/Genero/Hombre/Calzado-Hombre/Zapatillas-Hombre/"
        "Forum2000-Zapatillas-adidas-Unisex-Negro/p/ADJR1121"
    )
    notes = (
        'Precio de la tienda online; el "antes" es el precio normal tachado. Los cupones no '
        "se aplican. Sin elegir talla se sigue el precio más bajo entre las tallas con stock "
        "online (el stock de las tiendas físicas no cuenta)."
    )
