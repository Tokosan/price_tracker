"""Procesador de La Fortaleza (Punta Arenas; Jumpseller, sin Cloudflare → httpx directo)."""

from tracker.processors.jumpseller import JumpsellerProcessor


class LaFortalezaProcessor(JumpsellerProcessor):
    name = "lafortaleza"
    label = "La Fortaleza"
    host = "lafortalezapuq.cl"
    canonical_host = "www.lafortalezapuq.cl"
    home_url = "https://www.lafortalezapuq.cl/"
    example_url = "https://www.lafortalezapuq.cl/frosthaven"
    notes = "Tienda de Punta Arenas. Pega el link de un producto, no de una categoría."
