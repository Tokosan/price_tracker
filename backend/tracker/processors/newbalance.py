"""Procesador de New Balance Chile (newbalance.cl, Magento 2; mismo grupo que Sparta).

Todo lo común está en `MagentoProcessor`. La ficha no trae una marca de stock en texto:
siempre trae el formulario de compra, y el botón "Añadir al carrito" solo si hay stock
(`stock_marker = "cart_button"`). Un agotado completo no trae botón ni tallas, y un
configurable agotado tampoco trae precio. Las tallas vendibles vienen en el `jsonConfig`
("H4 / M5.5": talla de hombre y de mujer).
"""

from tracker.processors.magento import MagentoProcessor


class NewBalanceProcessor(MagentoProcessor):
    name = "newbalance"
    label = "New Balance"
    host = "newbalance.cl"
    stock_marker = "cart_button"
    home_url = "https://newbalance.cl/"
    example_url = (
        "https://newbalance.cl/zapatillas-urbanas-unisex-new-balance-530-bicolor-"
        "169000000mr530sg96.html"
    )
    notes = (
        'Precio de la ficha; el "precio habitual" tachado queda como precio antes. Cada '
        "color tiene su propio link. Sin elegir talla se sigue el precio más bajo entre las "
        "tallas con stock; la tienda no muestra las tallas agotadas."
    )
