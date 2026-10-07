"""Procesador de Tricot (tricot.cl, Salesforce Commerce Cloud).

Se lee `Product-Variation` (ver `SFCCVariationProcessor`). La ficha es
`/<slug>-<pid>.html` y `/<pid>.html` redirige a ella, con la query intacta. El pid del
link suele ser el de un maestro (un modelo en un color, con las tallas por elegir), y la
talla elegida va en la query (`?dwvar_683951_color=41&dwvar_683951_size=103`); cada talla
tiene además su propio pid de variante (`…-719657383.html`). Colores y tallas vienen
como códigos (`41`, `103`); los nombres están en `displayValue`.

`price.list` viene vacío aunque la ficha muestre un tachado: el precio Internet y el
normal están en `pricebookPrices` (`internetPrice` / `normalPrice`).
"""

import re

from tracker.processors.sfcc import SFCCVariationProcessor, list_price_if_higher
from tracker.processors.util import to_minor


class TricotProcessor(SFCCVariationProcessor):
    name = "tricot"
    label = "Tricot"
    hosts = frozenset({"www.tricot.cl", "tricot.cl"})
    canonical_host = "www.tricot.cl"
    site_id = "TRICOT_CL"
    # /<slug>-<pid>.html o /<pid>.html (las categorías no terminan en .html).
    path_re = re.compile(r"^/(?:(?P<slug>[^/]*?)-)?(?P<pid>\d{6,})\.html$", re.I)
    title_with_selection = True
    home_url = "https://www.tricot.cl/"
    example_url = "https://www.tricot.cl/poleron-mujer-clasico-costuras-683951.html"
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Puedes seguir cualquier talla (avisa si queda stock en alguna) o tallas puntuales, "
        "cada una por separado. Marca las que quieras."
    )
    notes = (
        "Precio Internet; el precio con Tarjeta Tricot no se guarda. Sin elegir talla se "
        "sigue si queda stock en alguna."
    )

    def canonical_path(self, m: re.Match) -> str:
        return f"/{m.group('pid')}.html"

    def prices(self, product: dict) -> tuple[int | None, int | None, str]:
        book = product.get("pricebookPrices")
        if not isinstance(book, dict) or not book.get("internetPrice"):
            return super().prices(product)
        price = to_minor((book.get("internetPrice") or {}).get("value"), "CLP")
        normal = to_minor((book.get("normalPrice") or {}).get("value"), "CLP")
        return price, list_price_if_higher(normal, price), "CLP"
