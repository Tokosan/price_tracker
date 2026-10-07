"""Base para tiendas de ropa y calzado en VTEX (Reebok, Levi's, Nike, …).

Cada talla (o talla y color) es un item de la ficha, con su `itemId`, su stock y su precio:
la talla va en `variant_id` y en `?skuId=`, como en Easy. Qué atributos tiene cada item lo
dice `items[].variations` (`["Talla"]`, `["Talla", "Color"]`, `["Cintura", "Largo"]` en
Levi's, `["talle", "color"]` en Nike), con el valor en `items[].<atributo>[0]`.

La etiqueta muestra el color sin nombre del atributo y lo omite si no cambia entre los items
de la ficha (en Nike cada color es su propia ficha y todos los items lo repiten): "Negro,
Talla M", "Talla H 7 / M 8.5", "Cintura 34, Largo 30". Las tallas se muestran siempre.

Con todas las tallas agotadas, la búsqueda por slug de Levi's da `[]`: se usa
`pagetype_fallback` (ver `vtex.py`) para que el producto quede agotado y no "no existe".

En estas tiendas una talla agotada suele volver al precio normal (`Price == ListPrice`)
mientras las que tienen stock siguen en oferta.
"""

import re

from tracker.processors.vtex import VtexProcessor

# Además de letras latinas, dígitos y guiones: guiones bajos (Ellus usa
# `jeans_hombre_straight_tiro_alto`) y lo que algunas tiendas arrastran del nombre del
# producto: un espacio duro (`logo\xa0-09tcr01965` en Tommy, `luka\xa077` en Nike), comillas
# tipográficas (`‘96` en Reebok) y `™` (American Eagle).
_PATH_RE = re.compile(r"/((?:[a-z0-9à-öø-ÿ_\xa0‘’™®]|-)+)/p/?", re.I)

# Nombre con que se muestra cada atributo (por su nombre en minúsculas).
_ATTR_LABEL = {"talla": "Talla", "talle": "Talla", "color": "Color"}


def _clean(value: object) -> str:
    """Sin espacios duros ni dobles y sin el punto final que Nike pone a sus colores."""
    return " ".join(str(value).split()).rstrip(".").strip()


class VtexApparelProcessor(VtexProcessor):
    supports_variants = True
    # Con todas las tallas agotadas, la búsqueda por slug puede dar `[]` (Levi's).
    pagetype_fallback = True
    path_re = _PATH_RE
    variants_title = "¿Qué talla seguir?"
    variants_hint = "Cada talla (o color) se sigue por separado. Marca las que quieras."

    def _attrs(self, item: dict) -> list[tuple[str, str]]:
        out = []
        for key in item.get("variations") or []:
            vals = item.get(key) or []
            value = _clean(vals[0]) if vals else ""
            if value:
                out.append((str(key).strip(), value))
        return out

    def item_labels(self, items: list[dict]) -> dict[str, str]:
        attrs = {str(it["itemId"]): self._attrs(it) for it in items}
        colors_seen = {
            v.lower() for pairs in attrs.values() for k, v in pairs if k.lower() == "color"
        }
        # El color se muestra si varía, o si es lo único que distingue (o describe) al item.
        show_color = len(colors_seen) > 1 or all(
            k.lower() == "color" for pairs in attrs.values() for k, _ in pairs
        )
        out = {}
        for vid, pairs in attrs.items():
            colors, others = [], []
            for key, value in pairs:
                k = key.lower()
                if k == "color" and not show_color:
                    continue
                if k == "color":
                    colors.append(value.capitalize() if value.isupper() else value)
                else:
                    name = _ATTR_LABEL.get(k, key.capitalize())
                    if value.lower().startswith(name.lower()):  # "TALLA ÚNICA"
                        others.append(value.capitalize())
                    else:
                        others.append(f"{name} {value}")
            out[vid] = ", ".join(colors + others)
        return out
