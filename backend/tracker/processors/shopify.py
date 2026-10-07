"""Base para tiendas Shopify (Piedra Bruja, Contrapunto, …), vía el JSON de la ficha.

`GET https://<host>/products/<handle>.js` es público (lo usa el propio tema para el
carrito y el selector de variantes) y responde 404 si el handle no existe. Trae el
producto con sus `variants[]`, cada una con `id`, `available`, `price`,
`compare_at_price` (el precio tachado) y `option1..3`. Los montos vienen **en centavos de
la moneda de la tienda, también en CLP** (`price: 2179000` = $21.790), y la moneda no
viene: la fija cada tienda (`currency`). Se prefiere a `/products/<handle>.json`, que no
trae `available` por variante.

La ficha también vive bajo una colección (`/collections/<x>/products/<handle>`): es el
mismo producto y se normaliza a `/products/<handle>`. La variante va en la URL como
`?variant=<id>` (el parámetro que entiende la ficha) y en `variant_id`. Sin `variant` se
sigue la primera variante (la ficha muestra la primera con stock, que cambia con el
inventario; para seguir un precio conviene una fija), como en VTEX. Si la tienda no
ofrece selector (`supports_variants = False`), se sigue siempre la primera.

Precio 0 (o negativo): sin stock es un agotado real (`sold_out_without_price`); con stock
es un producto gratuito (los torneos de Piedra Bruja) y `parse` lanza `NotFoundError`,
así que el alta lo rechaza en vez de dejar un seguimiento que daría anomalía en cada
lectura.

Cada tienda define `name`, `label`, `host` (sin www), `canonical_host` y sus metadatos.
"""

import json
import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, quote, unquote, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text
from tracker.processors.util import to_minor

log = logging.getLogger(__name__)

# Path de una ficha: /products/<handle>, opcionalmente bajo /collections/<colección>/.
# Colecciones (/collections/<x>), búsquedas, páginas y el carrito no matchean.
_PATH_RE = re.compile(r"(?:/collections/[^/]+)?/products/([\w%-]+)/?", re.I)
# El handle ya decodificado: letras, dígitos, `_` y `-` (así `%2E%2E` no pasa).
_HANDLE_RE = re.compile(r"[\w-]+")

# Título de la única variante de un producto sin opciones.
_DEFAULT_TITLE = "Default Title"


class ShopifyProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www), `canonical_host` y los metadatos."""

    host: str = ""
    canonical_host: str = ""
    currency: str = "CLP"  # moneda de la tienda (el JSON de la ficha no la trae)
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    platform = "Shopify"
    # API no oficial para el tracker: se mantiene el control de caídas. Sin precio y sin
    # stock es un agotado real (Shopify lista igual la variante agotada).
    sold_out_without_price = True

    def __init__(self) -> None:
        self._hosts = {self.host, f"www.{self.host}"}

    def _match(self, url: str) -> re.Match | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme.lower() not in ("http", "https"):
            return None
        if (parts.hostname or "") not in self._hosts:
            return None
        m = _PATH_RE.fullmatch(parts.path)
        if not m or not _HANDLE_RE.fullmatch(unquote(m.group(1))):
            return None
        return m

    def matches(self, url: str) -> bool:
        return bool(self._match(url))

    def normalize(self, url: str) -> ProductRef:
        m = self._match(url)
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        handle = quote(unquote(m.group(1)).lower(), safe="-_")
        variant = ""
        if self.supports_variants:
            variant = (parse_qs(urlsplit(url.strip()).query).get("variant") or [""])[0]
            # Solo dígitos ASCII ("٣" pasa `isdigit`); "007" y "7" son la misma variante.
            variant = str(int(variant)) if variant.isascii() and variant.isdigit() else ""
        return ProductRef(handle, self._url(handle, variant), variant)

    def _url(self, handle: str, variant: str = "") -> str:
        url = f"https://{self.canonical_host}/products/{handle}"
        return url + (f"?variant={variant}" if variant else "")

    def domain(self) -> str:
        return self.canonical_host

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text(f"https://{self.canonical_host}/products/{ref.external_id}.js")

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = _product(raw, self.label)
        if not self.supports_variants and len(product["variants"]) > 1:
            log.warning(
                "%s: %s tiene %d variantes y la tienda no tiene selector; se sigue la primera",
                self.name,
                ref.external_id,
                len(product["variants"]),
            )
        variant = _variant(product, ref)
        price = self._amount(variant.get("price"))
        if price is None or not isinstance(variant.get("available"), bool):
            # Respuesta incompleta: es un error de lectura, no un agotado (si no,
            # `sold_out_without_price` lo dejaría pasar y avisaría OUT_OF_STOCK).
            raise FetchError("la variante de Shopify no trae price o available")
        if price <= 0:
            if variant["available"]:
                # Gratis y con stock (los torneos de Piedra Bruja): no hay precio que
                # seguir, y aceptarlo daría una anomalía en cada lectura.
                raise NotFoundError("producto gratuito: no tiene precio que seguir")
            price = None  # sin stock es un agotado real (sold_out_without_price)
        listed = self._amount(variant.get("compare_at_price"))
        title = (product.get("title") or "").strip()
        if self.supports_variants and len(product.get("variants") or []) > 1:
            title = f"{title} ({_label(variant)})"
        return ScrapeResult(
            title=title,
            price=price,
            list_price=listed if listed and price is not None and listed > price else None,
            currency=self.currency,
            available=variant["available"],
            image_url=_image(variant, product),
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las variantes hermanas, cada una con su `?variant=` en la URL.

        Igual que en VTEX: si el link no trae `variant`, la actual (la primera) se devuelve
        con el suyo, para que al agregarla se siga esa y no la que la tienda liste primero
        más adelante. Con una sola variante se devuelve sin `variant` (`variant_id` vacío),
        para que el link limpio y el copiado con `?variant=` sean el mismo Product.
        """
        if not self.supports_variants:
            return []
        product = _product(raw, self.label)
        variants = [v for v in product.get("variants") or [] if str(v.get("id") or "").isdigit()]
        current = str(_variant(product, ref).get("id"))
        if len(variants) <= 1:
            label = _label(variants[0]) if variants else ""
            return [Variant(self._url(ref.external_id), label, ref.external_id, "", True)]
        out: list[Variant] = []
        for var in variants:
            vid = str(var["id"])
            label = _label(var)
            price = self._amount(var.get("price"))
            if price and price > 0:
                label += f": ${price:,}".replace(",", ".")
            if var.get("available") is not True:
                label += " (agotada)"
            url = self._url(ref.external_id, vid)
            out.append(Variant(url, label, ref.external_id, vid, vid == current))
        return sorted(out, key=lambda v: not v.selected)

    def _amount(self, cents) -> int | None:
        """Centavos de Shopify (enteros, también en CLP) → unidad mínima de la moneda."""
        if cents is None or cents == "" or isinstance(cents, bool):
            return None
        try:
            value = Decimal(str(cents).strip()) / 100
        except InvalidOperation:
            return None
        return to_minor(str(value), self.currency)


class ShopifyApparelProcessor(ShopifyProcessor):
    """Tiendas de ropa y calzado: cada variante (talla, color o ambos) se elige al agregar.

    Shopify limita por IP (429) con pocas peticiones, así que se leen cada 12 h.
    """

    check_interval = timedelta(hours=12)
    supports_variants = True
    variants_title = "¿Qué talla seguir?"
    variants_hint = (
        "Cada talla (o color) se sigue por separado, con su precio y su stock. Marca las "
        "que quieras."
    )


def _product(raw: str, label: str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        # Una página de Cloudflare o del tema en vez del JSON.
        raise FetchError(f"la ficha de {label} no devolvió JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("variants"), list):
        raise FetchError(f"respuesta inesperada de la ficha de {label}")
    if not data["variants"]:
        raise FetchError("el producto no trae variantes")
    return data


def _variant(product: dict, ref: ProductRef) -> dict:
    variants = product["variants"]
    if not ref.variant_id:
        return variants[0]
    for var in variants:
        if str(var.get("id")) == ref.variant_id:
            return var
    raise NotFoundError(f"la variante {ref.variant_id} ya no existe")


def _label(var: dict) -> str:
    """Nombre de la variante: sus opciones ("Rojo / M"), como la muestra la ficha."""
    title = (var.get("public_title") or var.get("title") or "").strip()
    if title and title != _DEFAULT_TITLE:
        return title
    options = [str(var.get(f"option{i}") or "").strip() for i in (1, 2, 3)]
    options = [o for o in options if o and o != _DEFAULT_TITLE]
    return " / ".join(options) if options else f"variante {var.get('id')}"


def _image(var: dict, product: dict) -> str | None:
    image = var.get("featured_image")
    src = image.get("src") if isinstance(image, dict) else None
    src = src or product.get("featured_image")
    if not isinstance(src, str) or not src:
        return None
    return f"https:{src}" if src.startswith("//") else src
