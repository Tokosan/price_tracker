"""Procesador de Salcobrand (salcobrand.cl, farmacia; Spree sobre Rails).

Se lee la ficha HTML `/products/<slug>`, que trae un JSON-LD con `@graph`: el nodo
`Product` (o `["Product", "Drug"]` en medicamentos) apunta por `@id` a su `Offer`. Ahí,
`price` es el **Precio Internet** (el que paga cualquiera en la web) y
`priceSpecification` trae el **Precio Farmacia** tachado (`priceType` StrikethroughPrice)
y el "Precio SBPay" (tarjeta propia de la cadena), que no se usa. `og:price:amount` es el
precio farmacia: tampoco sirve como precio.

Un producto puede tener varias variantes (SKU), todas en la misma URL: `?default_sku=<sku>`
elige cuál muestra la ficha, y el JSON-LD (`Product.sku`, precio y stock) pasa a ser el de
esa variante. Con un SKU que no es del producto la tienda no da error: muestra la primera
variante. Por eso el SKU del link va en `variant_id` y se comprueba contra `Product.sku`.
Las etiquetas del selector salen de `product_traker_data` (script de recomendaciones con
precio, stock, color y formato de cada SKU), que solo se usa para nombrar variantes.

Un slug inexistente redirige a `/404`, que responde HTTP 404.
"""

import html as htmllib
import json
import re
from urllib.parse import parse_qs, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import availability_in_stock, iter_json_ld, to_minor

_HOSTS = frozenset({"salcobrand.cl", "www.salcobrand.cl"})
_PATH_RE = re.compile(r"^/products/([a-z0-9-]+)/?$", re.I)
_OPTION_RE = re.compile(r"<option\b([^>]*\bsku=\"(\d+)\"[^>]*)>([^<]*)</option>")
_TRACKER_RE = re.compile(r"var product_traker_data = (\{.*?\});\s*\n")
_HEX_RE = re.compile(r"#[0-9a-f]{3,8}$", re.I)


class SalcobrandProcessor(Processor):
    name = "salcobrand"
    label = "Salcobrand"
    home_url = "https://salcobrand.cl/"
    example_url = "https://salcobrand.cl/products/pasta-dental-colgate-total-interdental-90-g"
    platform = "Spree (JSON-LD de la ficha)"
    supports_variants = True
    variants_title = "Variantes"
    variants_hint = "Cada variante (color o formato) se sigue por separado. Marca las que quieras."
    supports_list_price = True
    notes = (
        "Precio Internet; el Precio Farmacia va como precio normal tachado y el Precio SBPay "
        "(tarjeta de la cadena) no se guarda. Si un producto tiene varias variantes, se "
        "eligen al agregarlo y cada una se sigue por separado."
    )

    def _match(self, url: str) -> tuple[str, str] | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS:
            return None
        m = _PATH_RE.match(parts.path)
        if not m:
            return None
        sku = (parse_qs(parts.query).get("default_sku") or [""])[0].strip()
        return m.group(1).lower(), sku if sku.isdigit() else ""

    def matches(self, url: str) -> bool:
        return self._match(url) is not None

    def normalize(self, url: str) -> ProductRef:
        found = self._match(url)
        if not found:
            raise ValueError("no es una URL de producto de Salcobrand")
        slug, sku = found
        return ProductRef(slug, _url(slug, sku), sku)

    def domain(self) -> str:
        return "salcobrand.cl"

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(ref.canonical_url)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product, offer = _product_offer(raw)
        sku = str(product.get("sku") or "")
        if ref.variant_id and sku != ref.variant_id:
            # La tienda muestra la primera variante cuando el SKU ya no es del producto.
            raise NotFoundError(f"la variante {ref.variant_id} ya no existe en Salcobrand")
        currency = offer.get("priceCurrency") or "CLP"
        price = to_minor(offer.get("price"), currency)
        strike = _strikethrough(offer, currency)
        title = (product.get("name") or "").strip()
        variants = _variants(raw)
        if len(variants) > 1 and sku in variants:
            title = f"{title} ({variants[sku][0]})"
        images = product.get("image")
        image = images[0] if isinstance(images, list) and images else images
        return ScrapeResult(
            title=title,
            price=price,
            list_price=strike if strike and price is not None and strike > price else None,
            currency=currency,
            available=availability_in_stock(offer.get("availability")),
            image_url=image if isinstance(image, str) else None,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las variantes del producto, cada una con su `?default_sku=`.

        Con una sola variante se devuelve la URL sin `default_sku` (como en VTEX), para que
        el link limpio y el que trae el SKU sean el mismo producto. Con varias, la actual
        siempre lleva su SKU: se sigue esa variante fija y no la que la tienda muestre
        primero más adelante.
        """
        product, _ = _product_offer(raw)
        current = str(product.get("sku") or "")
        if ref.variant_id and current != ref.variant_id:
            raise NotFoundError(f"la variante {ref.variant_id} ya no existe en Salcobrand")
        variants = _variants(raw)
        slug = ref.external_id
        if len(variants) <= 1:
            label = variants[current][0] if current in variants else ""
            return [Variant(_url(slug), label, slug, "", True)]
        out = []
        for sku, (label, price, available) in variants.items():
            if price:
                label += f": ${price:,}".replace(",", ".")
            if available is False:
                label += " (agotada)"
            out.append(Variant(_url(slug, sku), label, slug, sku, sku == current))
        return sorted(out, key=lambda v: not v.selected)


def _url(slug: str, sku: str = "") -> str:
    return f"https://salcobrand.cl/products/{slug}" + (f"?default_sku={sku}" if sku else "")


def _types(node: dict) -> list:
    kind = node.get("@type")
    return kind if isinstance(kind, list) else [kind]


def _product_offer(raw: str) -> tuple[dict, dict]:
    """El `Product` del JSON-LD y su `Offer` (enlazada por `@id` o anidada)."""
    nodes = list(iter_json_ld(raw))
    product = next((n for n in nodes if "Product" in _types(n)), None)
    if product is None:
        # Un slug inexistente ya da 404 (redirige a /404): una página sin `Product` es
        # una ficha que cambió o vino incompleta, no un producto que dejó de existir.
        raise FetchError("la página de Salcobrand no trae el producto en su JSON-LD")
    offer = product.get("offers")
    if isinstance(offer, list):
        offer = offer[0] if offer else None
    if isinstance(offer, dict) and "Offer" not in _types(offer) and offer.get("@id"):
        offer = next(
            (n for n in nodes if "Offer" in _types(n) and n.get("@id") == offer["@id"]), None
        )
    if not isinstance(offer, dict) or "price" not in offer:
        raise FetchError("el JSON-LD de Salcobrand no trae la oferta del producto")
    return product, offer


def _strikethrough(offer: dict, currency: str) -> int | None:
    """Precio Farmacia: la especificación tachada (el "Precio SBPay" no tiene priceType)."""
    specs = offer.get("priceSpecification") or []
    for spec in specs if isinstance(specs, list) else [specs]:
        if isinstance(spec, dict) and str(spec.get("priceType") or "").endswith(
            "/StrikethroughPrice"
        ):
            return to_minor(spec.get("price"), spec.get("priceCurrency") or currency)
    return None


def _variants(raw: str) -> dict[str, tuple[str, int | None, bool | None]]:
    """{sku: (etiqueta, precio, disponible)} de las variantes de la ficha, en su orden.

    Los SKU salen de las `<option sku=…>` del selector de formato; color, precio y stock,
    de `product_traker_data` (si no está, la etiqueta es el texto de la opción). Una
    etiqueta repetida o vacía se completa con el SKU.
    """
    options = {sku: htmllib.unescape(text).strip() for _, sku, text in _OPTION_RE.findall(raw)}
    info = _tracker_products(raw)
    raw_labels = {}
    for sku, text in options.items():
        data = info.get(sku) or {}
        color = _HEX_RE.sub("", str(data.get("color") or "")).strip()
        size = str(data.get("size") or "").strip() or text
        raw_labels[sku] = ", ".join(v for v in (color, size) if v)
    values = list(raw_labels.values())
    out = {}
    for sku, lbl in raw_labels.items():
        if not lbl:
            lbl = f"SKU {sku}"
        elif values.count(lbl) > 1:
            lbl = f"{lbl}, SKU {sku}"
        data = info.get(sku) or {}
        available = data.get("isAvailable")
        out[sku] = (
            lbl,
            to_minor(data.get("price"), "CLP"),
            available if isinstance(available, bool) else None,
        )
    return out


def _tracker_products(raw: str) -> dict[str, dict]:
    m = _TRACKER_RE.search(raw)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    products = data.get("products") if isinstance(data, dict) else None
    return (
        {str(k): v for k, v in products.items() if isinstance(v, dict)}
        if isinstance(products, dict)
        else {}
    )
