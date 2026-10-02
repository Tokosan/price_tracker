"""Procesador de Jumbo (supermercado de Cencosud, plataforma VTEX)."""

from tracker.processors.vtex import VtexProcessor


class JumboProcessor(VtexProcessor):
    name = "jumbo"
    label = "Jumbo"
    host = "www.jumbo.cl"
    account = "jumbocl"
    home_url = "https://www.jumbo.cl/"
    example_url = "https://www.jumbo.cl/atun-robinson-crusoe-lomitos-en-agua-140-g-neto-2036254/p"
    notes = (
        "Precio online sin Tarjeta Cencosud (el precio con tarjeta no se guarda). "
        "Un producto sin precio y sin stock cuenta como agotado."
    )
