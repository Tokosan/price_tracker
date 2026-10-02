"""Procesador de Vudu Gaming (Jumpseller, sin Cloudflare → httpx directo)."""

from datetime import timedelta

from tracker.processors.jumpseller import JumpsellerProcessor


class VuduGamingProcessor(JumpsellerProcessor):
    name = "vudugaming"
    label = "Vudu Gaming"
    host = "vudugaming.cl"
    canonical_host = "www.vudugaming.cl"
    languages = ("en", "es")
    check_interval = timedelta(hours=6)
    home_url = "https://www.vudugaming.cl/"
    example_url = "https://www.vudugaming.cl/sierra-west-espanol"
    notes = (
        "Juegos de mesa y TCG. Pega el link de un producto, no de una categoría. Las "
        "preventas con reserva muestran el monto a abonar, no el precio total."
    )
