"""Procesador de Easy (mejoramiento del hogar de Cencosud, plataforma VTEX).

Cada color es un item de la ficha, con su propio `itemId` y stock, y todos comparten la
URL: el color va en `variant_id` y en `?skuId=`. El nombre del color solo viene en la API
(`items[].Color`).
"""

from tracker.processors.vtex import VtexProcessor


class EasyProcessor(VtexProcessor):
    name = "easy"
    label = "Easy"
    host = "www.easy.cl"
    account = "easycl"
    supports_variants = True
    variants_title = "Colores"
    variants_hint = "Cada color se sigue por separado. Marca los que quieras."
    home_url = "https://www.easy.cl/"
    example_url = "https://www.easy.cl/bateria-55ah-330cca-derecho-qs55-quick-start-1258746/p"
    notes = (
        "Precio online sin Tarjeta Cencosud (el precio con tarjeta no se guarda). "
        "Los colores de un producto se eligen al agregarlo y cada uno se sigue por separado. "
        "Un producto sin precio y sin stock cuenta como agotado."
    )

    def item_label(self, item: dict) -> str:
        """`Color[0]`; sin color, las demás `variations` salvo "Talla Única" (casi todas)."""
        colors = item.get("Color") or []
        if colors and str(colors[0]).strip():
            return str(colors[0]).strip()
        values = []
        for key in item.get("variations") or []:
            vals = item.get(key) or []
            value = str(vals[0]).strip() if vals else ""
            if value and value.lower() != "talla única":
                values.append(value)
        return ", ".join(values)
