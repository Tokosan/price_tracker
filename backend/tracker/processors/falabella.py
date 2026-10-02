"""Procesador de Falabella (falabella.com/falabella-cl), vía la API de la plataforma."""

from tracker.processors.falabella_platform import FalabellaPlatformProcessor


class FalabellaProcessor(FalabellaPlatformProcessor):
    name = "falabella"
    label = "Falabella"
    hosts = ("www.falabella.com", "falabella.com")
    canonical_host = "www.falabella.com"
    site = "falabella-cl"
    path_kind = "product"
    home_url = "https://www.falabella.com/falabella-cl"
    example_url = (
        "https://www.falabella.com/falabella-cl/product/80758957/"
        "55-mini-led-m70h-4k-samsung-vision-ai-smart-tv-2026/80758957"
    )
    notes = (
        "Precio internet (o el de evento, si hay), sin la tarjeta CMR: el precio CMR no se "
        'guarda. El precio "antes" es el normal tachado. Cada talla, color o medida se '
        "sigue por separado; un link sin SKU sigue la variante que muestra la ficha. "
        "Incluye los productos de vendedores externos (marketplace)."
    )
