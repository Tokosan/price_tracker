"""Base para tiendas VTEX (Jumbo, …), vía la API pública del catálogo.

`GET https://<cuenta>.vtexcommercestable.com.br/api/catalog_system/pub/products/search/<slug>/p`
responde sin clave ni cookies con una lista: `[]` si el slug no existe, o el producto con
sus `items` (SKU) y, por cada vendedor, la oferta (`commertialOffer`) con precio, precio
"antes" y stock. El HTML de la ficha sirve peor: Jumbo responde 404 en un agotado con
precio 0, mientras que la API sí lo lista.

Cada tienda solo define su `host` y su `account`. Si sus items son variantes elegibles
(p. ej. colores que comparten la ficha), activa `supports_variants` y redefine `item_label`:
`variant_id` es el `itemId`, que va en la URL como `?skuId=` (el parámetro que la propia
ficha de VTEX entiende), y el título lleva la etiqueta del item entre paréntesis.

Si el buscador de la tienda muestra slugs de otro catálogo (Santa Isabel muestra los de
Jumbo), `refid_fallback` busca por el sufijo numérico del slug (`alternateIds_RefId`)
cuando el slug no existe, y solo acepta un producto con ese RefId.
"""

import json
import re
from datetime import timedelta
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


class VtexProcessor(Processor):
    """Subclases: `name`, `label`, `host` (con www), `account` y los metadatos."""

    host: str = ""
    account: str = ""
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    # API no oficial: se mantiene el control de caídas. Con precio 0 y sin stock la
    # tienda no tiene precio que mostrar: es un agotado real, no un parseo roto.
    sold_out_without_price = True
    platform = "VTEX"
    # Si el slug no existe, buscar por su sufijo numérico (RefId) antes de darlo por perdido.
    refid_fallback: bool = False

    def __init__(self) -> None:
        bare = self.host.removeprefix("www.")
        # Ficha: /<slug>/p. Categorías (/despensa/conservas) y búsquedas no matchean. El
        # slug admite letras unicode (`panadol-para-niños-…`): se compara decodificado.
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(bare)}/((?:[^\W_]|-)+)/p/?(?:[?#].*)?$", re.I
        )

    def _match(self, url: str) -> re.Match | None:
        path, rest = re.match(r"([^?#]*)(.*)", url.strip(), re.S).groups()
        return self._url_re.match(unquote(path) + rest)

    def matches(self, url: str) -> bool:
        return bool(self._match(url))

    def normalize(self, url: str) -> ProductRef:
        m = self._match(url)
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        slug = m.group(1).lower()
        sku = ""
        if self.supports_variants:
            sku = (parse_qs(urlsplit(url.strip()).query).get("skuId") or [""])[0]
            sku = sku if sku.isdigit() else ""
        return ProductRef(slug, self._url(slug, sku), sku)

    def _url(self, slug: str, sku: str = "") -> str:
        return f"https://{self.host}/{quote(slug)}/p" + (f"?skuId={sku}" if sku else "")

    def domain(self) -> str:
        return f"{self.account}.vtexcommercestable.com.br"

    def search_url(self, slug: str) -> str:
        return f"https://{self.domain()}/api/catalog_system/pub/products/search/{quote(slug)}/p"

    def refid_url(self, refid: str) -> str:
        return (
            f"https://{self.domain()}/api/catalog_system/pub/products/search"
            f"?fq=alternateIds_RefId:{refid}"
        )

    async def fetch_raw(self, ref: ProductRef) -> str:
        raw = await get_text(self.search_url(ref.external_id))
        refid = _refid(ref.external_id)
        if self.refid_fallback and refid and raw.strip() == "[]":
            raw = await get_text(self.refid_url(refid))
        return raw

    def _product(self, raw: str, ref: ProductRef) -> dict:
        data = _products(raw, ref)
        if not self.refid_fallback:
            return data[0]
        refid = _refid(ref.external_id)
        for p in data:
            if (p.get("linkText") or "").lower() == ref.external_id:
                return p
        for p in data:
            if refid and refid in _product_refids(p):
                return p
        if refid:
            raise NotFoundError(f"{ref.external_id} no existe en el catálogo")
        return data[0]

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = self._product(raw, ref)
        item = _item(product, ref)
        offer = _offer(item)
        price = to_minor(offer.get("Price"), "CLP")
        if price is None or not isinstance(offer.get("IsAvailable"), bool):
            raise FetchError("la oferta de VTEX no trae Price o IsAvailable")
        available = offer["IsAvailable"] and (offer.get("AvailableQuantity") or 0) > 0
        if price == 0:
            # Sin stock, precio 0 es un agotado real (sold_out_without_price). Con stock
            # queda price=None, que el checker trata como anomalía.
            price = None
        listed = to_minor(offer.get("ListPrice"), "CLP")
        if not (listed and price is not None and listed > price):
            # Suposición, sin un caso real observado: una promoción del catálogo bajaría
            # `Price` y dejaría el precio previo en `PriceWithoutDiscount` en una tienda que
            # no usa `ListPrice` (Dr. Simi). En los productos VTEX revisados (Jumbo, Santa
            # Isabel, Easy, Dr. Simi) nunca se activa: vale lo mismo que `ListPrice`.
            listed = to_minor(offer.get("PriceWithoutDiscount"), "CLP")
        images = item.get("images") or []
        title = (product.get("productName") or "").strip()
        if self.supports_variants and len(product.get("items") or []) > 1:
            title = f"{title} ({self._labels(product)[str(item.get('itemId') or '')]})"
        return ScrapeResult(
            title=title,
            price=price,
            list_price=listed if listed and price is not None and listed > price else None,
            currency="CLP",
            available=available,
            image_url=images[0].get("imageUrl") if images else None,
        )

    def item_label(self, item: dict) -> str:
        """Etiqueta de un item en el selector de variantes."""
        return (item.get("name") or item.get("itemId") or "").strip()

    def _labels(self, product: dict) -> dict[str, str]:
        """Etiqueta de cada item por `itemId`; sin etiqueta o repetida, se agrega el SKU."""
        items = [it for it in product.get("items") or [] if it.get("itemId")]
        raw = {str(it["itemId"]): self.item_label(it) for it in items}
        repeated = {lbl for lbl in raw.values() if list(raw.values()).count(lbl) > 1}
        return {
            vid: (f"{lbl}, SKU {vid}" if lbl in repeated else lbl) if lbl else f"SKU {vid}"
            for vid, lbl in raw.items()
        }

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Los items hermanos, cada uno con su `?skuId=` en la URL.

        Si el link no trae `skuId`, el item actual (el primero) se devuelve con el suyo: al
        agregarlo se sigue ese item fijo, no el que la API liste primero más adelante. Con un
        solo item es al revés: se devuelve sin `skuId` (`variant_id` vacío).
        """
        if not self.supports_variants:
            return []
        product = self._product(raw, ref)
        items = product.get("items") or []
        if len(items) == 1:
            # Un solo item: el `skuId` del link no aporta nada. Se ofrece la forma sin
            # `skuId` (la UI no muestra selector con una opción, pero agrega esta URL), para
            # que el link limpio y el copiado del sitio, con `?skuId=`, sean el mismo Product.
            _item(product, ref)  # un skuId que no es el de su item sigue siendo NotFoundError
            label = self._labels(product).get(str(items[0].get("itemId") or ""), "")
            return [Variant(self._url(ref.external_id), label, ref.external_id, "", True)]
        if not items:
            return []
        current = str(_item(product, ref).get("itemId") or "")
        labels = self._labels(product)
        out: list[Variant] = []
        for it in items:
            vid = str(it.get("itemId") or "")
            if not vid:
                continue
            label = labels[vid]
            try:
                offer = _offer(it)
            except FetchError:
                offer = {}
            price = to_minor(offer.get("Price"), "CLP")
            if price:
                label += f": ${price:,}".replace(",", ".")
            if not (offer.get("IsAvailable") and (offer.get("AvailableQuantity") or 0) > 0):
                label += " (agotada)"
            if vid == current and ref.variant_id:
                url = ref.canonical_url
            else:
                url = self._url(ref.external_id, vid)
            out.append(Variant(url, label, ref.external_id, vid, vid == current))
        return sorted(out, key=lambda v: not v.selected)


# Sufijo numérico del slug (`…-1871480`), que en Cencosud es el RefId del producto. Cinco
# dígitos o más: los sufijos cortos (`…-500grs-2`) no son RefId.
_REFID_RE = re.compile(r"-(\d{5,})$")


def _refid(slug: str) -> str | None:
    m = _REFID_RE.search(slug)
    return m.group(1) if m else None


def _product_refids(product: dict) -> set[str]:
    refs = {str(product.get("productReference") or "")}
    for it in product.get("items") or []:
        for alt in it.get("referenceId") or []:
            if isinstance(alt, dict) and alt.get("Key") == "RefId":
                refs.add(str(alt.get("Value") or ""))
    return refs - {""}


def _products(raw: str, ref: ProductRef) -> list[dict]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("la API de VTEX no devolvió JSON") from exc
    if not isinstance(data, list):
        raise FetchError("respuesta inesperada de la API de VTEX")
    if not data:
        raise NotFoundError(f"{ref.external_id} no existe en el catálogo")
    return data


def _item(product: dict, ref: ProductRef) -> dict:
    items = product.get("items") or []
    if not items:
        raise FetchError("el producto no trae items")
    if not ref.variant_id:
        return items[0]
    for it in items:
        if str(it.get("itemId")) == ref.variant_id:
            return it
    raise NotFoundError(f"la variante {ref.variant_id} ya no existe")


def _offer(item: dict) -> dict:
    """La oferta del vendedor por defecto (o del primero).

    Sin vendedor u oferta la respuesta está incompleta: es un error de lectura, no un
    agotado (si no, `sold_out_without_price` lo dejaría pasar y avisaría OUT_OF_STOCK).
    """
    sellers = item.get("sellers") or []
    if not sellers:
        raise FetchError("el item no trae vendedores")
    seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0])
    offer = seller.get("commertialOffer")
    if not isinstance(offer, dict):
        raise FetchError("el vendedor no trae commertialOffer")
    return offer
