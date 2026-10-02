"""Procesador de Sodimac (sodimac.cl/sodimac-cl), vía la API de la plataforma Falabella."""

from tracker.processors.falabella_platform import FalabellaPlatformProcessor


class SodimacProcessor(FalabellaPlatformProcessor):
    name = "sodimac"
    label = "Sodimac"
    hosts = ("www.sodimac.cl", "sodimac.cl")
    canonical_host = "www.sodimac.cl"
    site = "sodimac-cl"
    path_kind = "articulo"
    home_url = "https://www.sodimac.cl/sodimac-cl"
    example_url = (
        "https://www.sodimac.cl/sodimac-cl/articulo/128506383/"
        "puerta-exterior-madera-pino-oregon-80x200-cm-modelo-4-natural/128506384"
    )
    notes = (
        "Precio internet (o el de evento, si hay), sin la tarjeta CMR: el precio CMR no se "
        'guarda. El precio "antes" es el normal tachado. Cada medida, color o formato tiene '
        "su propio precio y se sigue por separado. Si el link no trae SKU, se preselecciona "
        "la variante por defecto de la API, que puede no ser la medida que muestra la ficha: "
        "revisa la medida al agregar o pega el link con SKU. Como link extra de un producto "
        "ya seguido, un link sin SKU sigue esa variante por defecto, que puede cambiar. "
        "Incluye los productos de vendedores externos (marketplace)."
    )
