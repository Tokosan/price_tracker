"""Base para tiendas WordPress + WooCommerce (Ecofarmacias, Gato Arcano, …), vía la Store API.

`GET https://<host>/wp-json/wc/store/v1/products?slug=<slug>` es pública (la usa el
carrito de bloques de WooCommerce): responde una lista con el producto o `[]` (HTTP 200)
si el slug no existe. Los montos de `prices` son strings en la unidad menor que indique
`currency_minor_unit` ("2000" con 0 decimales = $2.000), igual que lo guarda el tracker.

Productos variables (`type: variable`): el padre solo trae el precio mínimo y un stock
que puede quedar desactualizado (un padre "en stock" con todas sus variaciones agotadas),
así que se piden también las variaciones (`?type=variation&include=<ids>`), cada una con
su precio, stock y `permalink`. El permalink de una variación es la ficha con la selección
en la query (`/producto/<slug>/?attribute_color=NI%C3%91A`), que la propia ficha entiende.
La selección va en la URL tal cual y en `variant_id` normalizada (`color=nina`: sin
mayúsculas ni tildes), para que un link copiado a mano y el del selector sean el mismo
Product. Un link puede elegir solo algunos atributos: se sigue la primera variación
compatible. Sin selección se sigue la primera variación, como en VTEX. `fetch_raw` junta ambas respuestas en un JSON
`{"products": [...], "variations": [...]}`, que es lo que se guarda como fixture.

Cada tienda define `name`, `label`, `host` (sin www), `canonical_host` y sus metadatos; si
sus fichas no viven en `/producto/`, también `product_base`.
"""

import html as htmllib
import json
import logging
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

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

# Máximo de variaciones que se piden (el `per_page` máximo de la Store API).
_MAX_VARIATIONS = 100


class WooCommerceProcessor(Processor):
    """Subclases: `name`, `label`, `host` (sin www), `canonical_host` y los metadatos."""

    host: str = ""
    canonical_host: str = ""
    product_base: str = "producto"  # base de las fichas: /producto/<slug>/
    check_interval = timedelta(hours=6)
    fixture_ext = "json"
    platform = "WooCommerce"
    # API no oficial para el tracker: se mantiene el control de caídas. Sin precio y sin
    # stock es un agotado real (una variación agotada puede venir sin precio).
    sold_out_without_price = True

    def __init__(self) -> None:
        # Ficha: /producto/<slug>/. Categorías (/categoria-producto/…), etiquetas y
        # búsquedas no matchean.
        self._url_re = re.compile(
            rf"^https?://(?:www\.)?{re.escape(self.host)}/{re.escape(self.product_base)}/"
            r"([a-z0-9_%][a-z0-9_%-]*)/?(?:[?#].*)?$",
            re.I,
        )

    def matches(self, url: str) -> bool:
        return bool(self._url_re.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        m = self._url_re.match(url.strip())
        if not m:
            raise ValueError(f"no es una URL de producto de {self.label}")
        slug = m.group(1).lower()
        selection: dict[str, str] = {}
        if self.supports_variants:
            selection = _query_selection(urlsplit(url.strip()).query)
        return ProductRef(slug, self._url(slug, selection), variant_key(selection))

    def _url(self, slug: str, selection: dict[str, str] | None = None) -> str:
        url = f"https://{self.canonical_host}/{self.product_base}/{slug}/"
        if selection:
            url += "?" + urlencode(sorted((f"attribute_{k}", v) for k, v in selection.items()))
        return url

    def domain(self) -> str:
        return self.canonical_host

    def api_url(self) -> str:
        return f"https://{self.canonical_host}/wp-json/wc/store/v1/products"

    async def fetch_raw(self, ref: ProductRef) -> str:
        _check_slug(ref)
        raw = await get_text(self.api_url(), params={"slug": unquote(ref.external_id)})
        products = _json_list(raw)
        variations: list = []
        product = _pick(products, ref) if products else None
        if product and product.get("type") == "variable":
            ids = _variation_ids(product)
            if len(ids) > _MAX_VARIATIONS:
                log.warning(
                    "%s: %s tiene %d variaciones; se leen las primeras %d",
                    self.name,
                    ref.external_id,
                    len(ids),
                    _MAX_VARIATIONS,
                )
                ids = ids[:_MAX_VARIATIONS]
            if ids:
                params = {
                    "type": "variation",
                    "include": ",".join(ids),
                    "per_page": str(_MAX_VARIATIONS),
                }
                variations = _json_list(await get_text(self.api_url(), params=params))
        return json.dumps({"products": products, "variations": variations}, ensure_ascii=False)

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product, variations = self._load(raw, ref)
        item = _select(variations, ref, product) if variations else product
        if variations is None and ref.variant_id:
            # Un producto simple no tiene variaciones: un link con selección vieja no
            # puede leer otra cosa que el producto.
            raise NotFoundError(f"la variante {ref.variant_id} ya no existe")
        prices = item.get("prices")
        if not isinstance(prices, dict) or not isinstance(item.get("is_in_stock"), bool):
            # Respuesta incompleta: es un error de lectura, no un agotado (si no,
            # `sold_out_without_price` lo dejaría pasar y avisaría OUT_OF_STOCK).
            raise FetchError("el producto de la Store API no trae prices o is_in_stock")
        currency = (prices.get("currency_code") or "CLP").upper()
        price = _amount(prices, "price", currency)
        regular = _amount(prices, "regular_price", currency)
        purchasable = item.get("is_purchasable") is not False
        available = item.get("is_in_stock") is True and purchasable
        if price == 0 or not purchasable:
            # Con stock, precio 0 queda en None (anomalía); sin stock es un agotado real.
            # Un producto que no se puede comprar ("próximamente") trae un precio de
            # relleno ("0" o "1" en Gato Arcano) que nadie paga: tampoco es un precio.
            price = None
        title = htmllib.unescape(product.get("name") or "").strip()
        if self.supports_variants and variations and len(variations) > 1:
            title = f"{title} ({_label(item, product)})"
        images = item.get("images") or product.get("images") or []
        image = images[0].get("src") if images and isinstance(images[0], dict) else None
        return ScrapeResult(
            title=title,
            price=price,
            list_price=regular if regular and price is not None and regular > price else None,
            currency=currency,
            available=available,
            image_url=image,
        )

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las variaciones hermanas, cada una con su selección en la URL.

        Si el link no trae selección, la variación actual (la primera) se devuelve con la
        suya, para que al agregarla se siga esa y no la que la tienda liste primero más
        adelante. La URL y el `variant_id` salen siempre del permalink de la variación, así
        que son los mismos que da `normalize` sobre esa URL.

        Con una sola variación se devuelve sin selección (`variant_id` vacío), como en VTEX.
        Si el link traía selección, `/resolve` ya creó un Product con ella y el selector
        ofrece el link limpio: ese Product queda sin seguir (no se lee) y el que se agrega es
        el limpio. No se puede unificar en `normalize`, que no sabe cuántas variaciones hay.
        """
        if not self.supports_variants:
            return []
        product, variations = self._load(raw, ref)
        if not variations:
            return []
        current = _select(variations, ref, product)
        if len(variations) == 1:
            label = _label(current, product)
            return [Variant(self._url(ref.external_id), label, ref.external_id, "", True)]
        current_key = variant_key(_variation_selection(current, product))
        out: list[Variant] = []
        for var in variations:
            selection = _variation_selection(var, product)
            key = variant_key(selection)
            if not key:
                continue
            prices = var.get("prices") or {}
            price = _amount(prices, "price", (prices.get("currency_code") or "CLP").upper())
            label = _label(var, product)
            if price:
                label += f": ${price:,}".replace(",", ".")
            if not (var.get("is_in_stock") is True and var.get("is_purchasable") is not False):
                label += " (agotada)"
            url = self._url(ref.external_id, selection)
            out.append(Variant(url, label, ref.external_id, key, key == current_key))
        return sorted(out, key=lambda v: not v.selected)

    def _load(self, raw: str, ref: ProductRef) -> tuple[dict, list[dict] | None]:
        """(producto, variaciones ordenadas como en el padre; None si no es variable)."""
        _check_slug(ref)
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError(f"la Store API de {self.label} no devolvió JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise FetchError(f"respuesta inesperada de la Store API de {self.label}")
        if not data["products"]:
            raise NotFoundError(f"{ref.external_id} no existe en {self.label}")
        product = _pick(data["products"], ref)
        if product.get("type") != "variable" or not _variation_ids(product):
            return product, None
        by_id = {
            str(v.get("id")): v
            for v in data.get("variations") or []
            if isinstance(v, dict) and v.get("id")
        }
        variations = [by_id[i] for i in _variation_ids(product) if i in by_id]
        if not variations:
            raise FetchError("el producto variable no trae sus variaciones")
        return product, variations


def _check_slug(ref: ProductRef) -> None:
    # Productos enviados a la papelera: WordPress les deja el slug `__trashed[-N]` y
    # algunas tiendas los siguen enlazando.
    if ref.external_id.startswith("__trashed"):
        raise NotFoundError(f"{ref.external_id} es un producto eliminado")


def _json_list(raw: str) -> list:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("la Store API no devolvió JSON") from exc
    if not isinstance(data, list):
        raise FetchError("respuesta inesperada de la Store API")
    return data


def _pick(products: list, ref: ProductRef) -> dict:
    slug = unquote(ref.external_id).lower()
    for p in products:
        if isinstance(p, dict) and unquote(str(p.get("slug") or "")).lower() == slug:
            return p
    # Sin el producto pedido la respuesta no sirve: p. ej. un caché o WAF que borra
    # `?slug=` y la API lista los últimos productos (se leería el precio de otro).
    raise FetchError(f"la Store API no devolvió el producto {ref.external_id}")


def _variation_ids(product: dict) -> list[str]:
    return [
        str(v["id"])
        for v in product.get("variations") or []
        if isinstance(v, dict) and str(v.get("id") or "").isdigit()
    ]


def _amount(prices: dict, key: str, currency: str) -> int | None:
    """Monto de la Store API (unidad menor según `currency_minor_unit`) → unidad mínima ISO."""
    value = prices.get(key)
    if value is None or value == "":
        return None
    try:
        minor_unit = int(prices.get("currency_minor_unit") or 0)
        amount = Decimal(str(value).strip()) / (Decimal(10) ** minor_unit)
    except (InvalidOperation, ValueError):
        return None
    return to_minor(str(amount), currency)


def _slug(text: str) -> str:
    """Forma comparable de un atributo o valor ("NIÑA" ≈ "nina", "Tamaño" ≈ "tamano")."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def variant_key(selection: dict[str, str]) -> str:
    """{atributo: valor} → "atributo=valor&…" normalizado y ordenado (el `variant_id`).

    "COLOR=NIÑA" y "color=nina" dan lo mismo ("color=nina"): la ficha no distingue.
    """
    pairs = {_slug(k): _slug(v) for k, v in selection.items()}
    return urlencode(sorted((k, v) for k, v in pairs.items() if k and v), quote_via=quote)


def decode_selection(variant_id: str) -> dict[str, str]:
    return dict(parse_qsl(variant_id)) if variant_id else {}


def _query_selection(query: str) -> dict[str, str]:
    """Los `attribute_<nombre>=<valor>` de una URL de ficha (los vacíos no eligen nada)."""
    out = {}
    for key, value in parse_qsl(query):
        if key.lower().startswith("attribute_") and value.strip():
            out[key[len("attribute_") :].lower()] = value.strip()
    return out


def _variation_selection(var: dict, product: dict) -> dict[str, str]:
    """Selección de una variación: la query de su permalink o, si no trae, sus atributos."""
    selection = _query_selection(urlsplit(var.get("permalink") or "").query)
    if selection:
        return selection
    for ref in product.get("variations") or []:
        if isinstance(ref, dict) and str(ref.get("id")) == str(var.get("id")):
            return {
                _slug(a.get("name") or ""): a["value"]
                for a in ref.get("attributes") or []
                if isinstance(a, dict) and a.get("name") and a.get("value")
            }
    return {}


def _select(variations: list[dict], ref: ProductRef, product: dict) -> dict:
    """La primera variación compatible con la selección del link (la primera si no trae).

    Compatible: coincide en todos los atributos que tienen ambos y comparte al menos uno.
    Un link puede elegir solo algunos atributos, y un atributo que la variación deja vacío
    ("cualquiera") no aparece en su permalink y acepta cualquier valor.
    """
    if not ref.variant_id:
        return variations[0]
    wanted = decode_selection(ref.variant_id)
    for var in variations:
        have = dict(parse_qsl(variant_key(_variation_selection(var, product))))
        common = wanted.keys() & have.keys()
        if common and all(wanted[k] == have[k] for k in common):
            return var
    raise NotFoundError(f"la variante {ref.variant_id} ya no existe")


def _label(var: dict, product: dict) -> str:
    """Nombre de una variación: los valores de sus atributos, como los muestra el padre."""
    for ref in product.get("variations") or []:
        if isinstance(ref, dict) and str(ref.get("id")) == str(var.get("id")):
            values = [
                str(a["value"]).strip()
                for a in ref.get("attributes") or []
                if isinstance(a, dict) and a.get("value")
            ]
            if values:
                return ", ".join(values)
    # Sin atributos en el padre, la selección del permalink. Un atributo global
    # (`pa_<nombre>`) trae el slug del término: "yuya-okita" → "Yuya Okita".
    values = [
        v.replace("-", " ").title() if k.startswith("pa_") else v
        for k, v in _variation_selection(var, product).items()
    ]
    return ", ".join(values) if values else f"variación {var.get('id')}"
