"""Procesador de Santa Isabel (supermercado de Cencosud, plataforma VTEX).

Su buscador muestra slugs del catálogo de Jumbo: un link armado así puede no existir
en Santa Isabel (la API da `[]` y la ficha 404). Por eso se activa el respaldo por el
sufijo numérico del slug (RefId), que sí es común a los dos catálogos.
"""

from tracker.processors.vtex import VtexProcessor


class SantaIsabelProcessor(VtexProcessor):
    name = "santaisabel"
    label = "Santa Isabel"
    host = "www.santaisabel.cl"
    account = "santaisabel"
    refid_fallback = True
    home_url = "https://www.santaisabel.cl/"
    example_url = "https://www.santaisabel.cl/atun-antartic-lomitos-en-agua-91-g-drenado-1989506/p"
    notes = (
        "Precio online sin Tarjeta Cencosud (el precio con tarjeta no se guarda). "
        "Un producto sin precio y sin stock cuenta como agotado. Si el link trae un slug "
        "de Jumbo que Santa Isabel no tiene, se busca el mismo producto por su código."
    )
