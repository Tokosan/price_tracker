"""Procesador de IKEA Chile. Cada variante tiene su URL y número de artículo."""

import json
import re
from datetime import timedelta

from tracker.processors.base import Processor, ProductRef, ScrapeResult, Variant
from tracker.processors.http import get_text
from tracker.processors.util import (
    availability_in_stock,
    find_ld_product,
    first_offer,
    to_minor,
)

# Artículos simples tienen 8 dígitos; las combinaciones ("sistemas") llevan una "s".
_URL_RE = re.compile(
    r"^https?://(?:www\.)?ikea\.com/cl/es/p/([a-z0-9-]+?)-(s?\d{8})/?(?:[?#].*)?$", re.I
)
_PICKER_KEY = '"productStylePickerProps":'
_LINK_RE = re.compile(r"https://www\.ikea\.com/cl/es/p/([a-z0-9-]+?)-(s?\d{8})/")


class IkeaProcessor(Processor):
    name = "ikea"
    label = "IKEA Chile"
    check_interval = timedelta(hours=6)
    home_url = "https://www.ikea.com/cl/es/"
    example_url = "https://www.ikea.com/cl/es/p/billy-estante-blanco-00263850/"
    platform = "IKEA"
    supports_variants = True
    supports_list_price = False
    notes = (
        "El selector de variantes muestra los colores; otras medidas se agregan pegando "
        "su propio link. Stock de la venta online."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = _URL_RE.match(url.strip())
        if not m:
            raise ValueError("no es una URL de producto de IKEA Chile")
        slug, article = m.group(1).lower(), m.group(2).lower()
        return ProductRef(article, f"https://www.ikea.com/cl/es/p/{slug}-{article}/")

    def domain(self) -> str:
        return "www.ikea.com"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = find_ld_product(raw)
        if not product:
            return ScrapeResult("", None, None, "CLP", False, None)
        offer = first_offer(product) or {}
        currency = offer.get("priceCurrency") or "CLP"
        image = product.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("contentUrl") or image.get("url")
        return ScrapeResult(
            title=product.get("name") or "",
            price=to_minor(offer.get("price"), currency),
            list_price=None,  # el JSON-LD de IKEA no trae "precio anterior"
            currency=currency,
            available=availability_in_stock(offer.get("availability")),
            image_url=image,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Variantes hermanas desde el selector de estilo embebido en la página.

        `productStylePickerProps.variationStyles[].allOptions[]` trae una opción
        por valor de cada dimensión (color, medida…) con su URL y número de
        artículo. Si falta, se cae a los links del HTML con el mismo nombre base.
        """
        variants: dict[str, Variant] = {}
        idx = raw.find(_PICKER_KEY)
        if idx >= 0:
            try:
                picker, _ = json.JSONDecoder().raw_decode(raw, idx + len(_PICKER_KEY))
            except ValueError:
                picker = {}
            styles = picker.get("variationStyles") or []
            for style in styles:
                # Con más de una dimensión (color y medida) se antepone cuál es.
                dim = (style.get("title") or "").replace("Elige ", "").capitalize()
                for opt in style.get("allOptions") or []:
                    url = opt.get("url") or ""
                    if not self.matches(url):
                        continue
                    vref = self.normalize(url)
                    label = opt.get("title") or vref.external_id
                    if len(styles) > 1 and dim:
                        label = f"{dim}: {label}"
                    if vref.external_id in variants:
                        continue
                    variants[vref.external_id] = Variant(
                        url=vref.canonical_url,
                        label=label,
                        external_id=vref.external_id,
                        selected=vref.external_id == ref.external_id,
                    )
        if not variants:
            base = _family(ref.canonical_url)
            for slug, article in _LINK_RE.findall(raw):
                if _family(slug) != base or article in variants:
                    continue
                url = f"https://www.ikea.com/cl/es/p/{slug}-{article}/"
                variants[article] = Variant(
                    url=url,
                    label=slug.replace("-", " "),
                    external_id=article,
                    selected=article == ref.external_id,
                )
        if ref.external_id not in variants and variants:
            variants[ref.external_id] = Variant(
                ref.canonical_url, "Actual", ref.external_id, selected=True
            )
        return sorted(variants.values(), key=lambda v: (not v.selected, v.label))


def _family(url_or_slug: str) -> str:
    """ "…/p/billy-estante-blanco-00263850/" → "billy-estante"."""
    slug = url_or_slug.rstrip("/").rsplit("/", 1)[-1]
    parts = slug.split("-")
    return "-".join(parts[:2])
