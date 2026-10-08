"""Procesador de Xtrem (xtrem.cl, mochilas y bolsos; Shopify headless).

Todo lo común está en `ShopifyProcessor`. El front es Next.js (Builder.io) en Vercel: el
`.js` de la ficha se pide al dominio del checkout (`checkout.xtrem.cl` =
`xtremcl.myshopify.com`). Cada color es su propio producto, con una sola variante; casi la
mitad del catálogo trae precio tachado (`compare_at_price`).
"""

from tracker.processors.shopify import ShopifyProcessor


class XtremProcessor(ShopifyProcessor):
    name = "xtrem"
    label = "Xtrem"
    host = "xtrem.cl"
    canonical_host = "xtrem.cl"
    api_host = "checkout.xtrem.cl"
    home_url = "https://xtrem.cl/"
    example_url = "https://xtrem.cl/products/set-mochila-lonchera-estuche-max-pack-negro-rojo"
    notes = (
        'Mochilas, bolsos y accesorios. Precio de la ficha; el tachado queda como precio "antes". '
        "Cada color tiene su propio link."
    )
