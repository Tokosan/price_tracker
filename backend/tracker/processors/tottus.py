"""Procesador de Tottus (tottus.cl/tottus-cl), vía la API de la plataforma Falabella.

La API exige `exp=to_com`, `pgid=34` y las zonas de despacho que usa la ficha. Sin
`exp` responde `NOT_FOUND`; con zonas que no sirven, todo sale `OUT_OF_STOCK` (con la
variante y su precio, sin `isPurchaseable`). Las zonas quedan fijas aquí: si Tottus
las cambia, los productos pasarían a "agotado" sin error de lectura. Para notarlo se
deja un `warning` cuando un producto que esta instancia leyó en stock pasa a agotado.
"""

import logging

from tracker.processors.base import ProductRef, ScrapeResult
from tracker.processors.falabella_platform import FalabellaPlatformProcessor

log = logging.getLogger(__name__)

# Zonas de la ficha de Tottus (copiadas de `pageProps.apiUrl` el 2026-10-02).
ZONES = (
    "PCL6672",
    "PCL1223",
    "PCL2976",
    "PCL3651",
    "PCL3887",
    "PCL6655",
    "PCL2709",
    "PCL2829",
    "PCL3505",
    "PCL3136",
    "PCL4992",
    "PCL5127",
    "PCL6985",
    "PCL6702",
    "PCL1486",
    "PCL3031",
    "PCL1839",
    "PCL3676",
    "PCL3139",
    "PCL2992",
    "PCL2269",
    "PCL6668",
    "PCL4976",
    "PCL651",
    "LEG_TOTTUS_DOMINICOS_1",
    "PCL596",
    "PCL6641",
    "PCL226",
    "PCL108",
    "PCL2288",
    "PCL3232",
    "PCL3145",
    "PCL1394",
    "PCL5090",
    "PCL5234",
    "PCL2792",
)


class TottusProcessor(FalabellaPlatformProcessor):
    name = "tottus"
    label = "Tottus"
    hosts = ("www.tottus.cl", "tottus.cl")
    canonical_host = "www.tottus.cl"
    site = "tottus-cl"
    path_kind = "articulo"
    extra_params = (("exp", "to_com"), ("pgid", "34"), ("zones", ",".join(ZONES)))
    home_url = "https://www.tottus.cl/tottus-cl"
    example_url = (
        "https://www.tottus.cl/tottus-cl/articulo/128289122/"
        "leche-semidescremada-uht-surlat-1-lt/128289124"
    )
    notes = (
        "Precio internet, sin la tarjeta CMR: el precio CMR no se guarda. El precio "
        '"antes" es el normal tachado. El stock sale de las zonas de despacho que usa la '
        "página, fijas en el código: si Tottus las cambia, los productos "
        "pueden aparecer agotados sin estarlo (queda un aviso en el log)."
    )

    def __init__(self) -> None:
        super().__init__()
        # (external_id, variant_id) → si la última lectura de este proceso tenía stock.
        self._last_available: dict[tuple[str, str], bool] = {}

    async def fetch(self, ref: ProductRef) -> ScrapeResult:
        result = await super().fetch(ref)
        key = (ref.external_id, ref.variant_id)
        if self._last_available.get(key) and not result.available:
            log.warning(
                "Tottus: %s pasó de en stock a agotado; si pasa con muchos productos a la "
                "vez, revisa las zonas (ZONES en tracker/processors/tottus.py)",
                ref.canonical_url,
            )
        self._last_available[key] = result.available
        return result
