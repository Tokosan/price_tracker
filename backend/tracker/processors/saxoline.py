"""Procesador de Saxoline (saxoline.cl, mochilas y maletas; Shopify headless).

Todo lo común está en `ShopifyProcessor`. Igual que Xtrem: el front es Next.js en Vercel y
el `.js` de la ficha se pide al dominio del checkout (`checkout.saxoline.cl` =
`saxolinecl.myshopify.com`). Cada color es su propio producto, con una sola variante.
"""

from tracker.processors.shopify import ShopifyProcessor


class SaxolineProcessor(ShopifyProcessor):
    name = "saxoline"
    label = "Saxoline"
    host = "saxoline.cl"
    canonical_host = "saxoline.cl"
    api_host = "checkout.saxoline.cl"
    home_url = "https://saxoline.cl/"
    example_url = "https://saxoline.cl/products/mochila-viaje-daynight-negra-17"
    notes = (
        'Mochilas y maletas. Precio de la ficha; el tachado queda como precio "antes". '
        "Cada color tiene su propio link."
    )
