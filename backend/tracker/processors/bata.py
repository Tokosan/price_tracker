"""Procesador de Bata Chile (bata.com/cl, Salesforce Commerce Cloud; incluye North Star,
Weinbrenner, Bubblegummers y las otras marcas que vende).

Se lee `Product-Variation` (ver `SFCCVariationProcessor`). Cloudflare bloquea el
fingerprint TLS de httpx (403), así que se pide con curl_cffi imitando a Chrome.

Los pid tienen guiones bajos: `701M_2024_9136031` es un grupo de variación (un modelo en
un color, con las tallas por elegir), `701M_2024_9136031_08` una talla de ese grupo y
`701M_079130316208IR` el maestro de todos los colores. En los `dwvar_` el pid va con los
`_` duplicados (`dwvar_701M__2024__9136031_size=9380`). La ficha es
`/cl/<categorías>/<slug>-<pid>.html`, y `/cl/<pid>.html` redirige a ella con la query.

`Product-Variation` da 500 con el pid de una talla, así que el link de una talla se sigue
como el de su grupo (sin talla elegida); la talla se elige en el selector. Cada color es su
propio grupo: el selector solo cambia la talla.
"""

import re

from tracker.processors.http import get_text_impersonate
from tracker.processors.sfcc import SFCCVariationProcessor


class BataProcessor(SFCCVariationProcessor):
    name = "bata"
    label = "Bata"
    hosts = frozenset({"www.bata.com"})
    canonical_host = "www.bata.com"
    site_id = "bata-cl"
    locale = "es_CL"
    # El sufijo `_NN` (talla) queda fuera del pid: se sigue el grupo.
    path_re = re.compile(
        r"^/cl/(?:[^/]+/)*(?:(?P<slug>[^/]*?)-)?"
        r"(?P<pid>\d{3}[a-z]_[0-9a-z]+(?:_\d{4,})?)(?:_\d{2})?\.html$",
        re.I,
    )
    variant_attrs = ("size",)
    title_with_selection = True
    home_url = "https://www.bata.com/cl/"
    example_url = (
        "https://www.bata.com/cl/mujer/vestuario/polars/"
        "polar-mujer-weinbrenner-cota--701M_2024_9136031.html"
    )
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (avisa si queda stock en alguna) o tallas puntuales, "
        "cada una por separado. Marca las que quieras."
    )
    notes = (
        "Incluye North Star, Weinbrenner y las otras marcas de bata.com/cl. Sin elegir talla "
        "se sigue si queda stock en alguna; cada color tiene su propio link."
    )

    def pid_from_match(self, m: re.Match) -> str:
        return m.group("pid").upper()

    def canonical_path(self, m: re.Match) -> str:
        return f"/cl/{self.pid_from_match(m)}.html"

    async def http_get(self, url: str, params: dict | None = None) -> str:
        return await get_text_impersonate(url, params=params)
