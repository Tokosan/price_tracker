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
        "variantes (opciones) no se pueden elegir: se sigue la variante por defecto. En las "
        "preventas con reserva (100 % / 50 %) se sigue el precio total, no el abono."
    )
