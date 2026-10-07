"""Procesador de Nike Chile (nike.cl, plataforma VTEX, cuenta `nikeclprod`).

`www.nike.cl` está detrás de Cloudflare y responde 403 a httpx, pero la API del catálogo
se lee por `nikeclprod.vtexcommercestable.com.br`, que no pasa por Cloudflare. Ojo: la
cuenta `nikecl` también responde, pero con otro catálogo (sin las fichas actuales); la de
la tienda es `nikeclprod` (`account` en el HTML de la ficha). Cada color es su propia ficha y los items son las
tallas (`talle`, `color`), con el color terminado en punto (`Negro.`).
"""

from tracker.processors.vtex_apparel import VtexApparelProcessor


class NikeProcessor(VtexApparelProcessor):
    name = "nike"
    label = "Nike"
    host = "www.nike.cl"
    account = "nikeclprod"
    home_url = "https://www.nike.cl/"
    example_url = "https://www.nike.cl/hq3950-002-air-jordan-mvp-92/p"
    notes = (
        "Precio online de cada talla; el precio normal tachado se guarda como precio "
        '"antes". Cada talla se sigue por separado.'
    )
