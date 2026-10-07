"""Procesador de Belsport (www.belsport.cl), sobre SAP Commerce (API OCC del grupo Yaneken).

Todo lo común está en `SapCommerceProcessor`. Comparte la API con Bold (`api-prd.ynk.cl`),
con su propio `baseSite`: un código de Bold no existe en Belsport y viceversa.
"""

from tracker.processors.sapcommerce import SapCommerceProcessor


class BelsportProcessor(SapCommerceProcessor):
    name = "belsport"
    label = "Belsport"
    hosts = ("www.belsport.cl", "belsport.cl")
    canonical_host = "www.belsport.cl"
    api_base = "https://api-prd.ynk.cl/rest/v2"
    base_site = "belsportb2cstore"
    home_url = "https://www.belsport.cl/"
    example_url = (
        "https://www.belsport.cl/Categories/Genero/Mujer/Zapatillas-Mujer/"
        "Zapatillas-Urbanas-Mujer/Zapatillas-Nike-Mujer-Court-Vision-Low-Blancas/p/NIDH3158100"
    )
    notes = (
        'Precio de la tienda online; el "antes" es el precio normal tachado. Los cupones no '
        "se aplican. Sin elegir talla se sigue el precio más bajo entre las tallas con stock "
        "online (el stock de las tiendas físicas no cuenta)."
    )
