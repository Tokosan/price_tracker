"""Utilidades de parseo compartidas."""

import json
import re
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation

_LD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I
)

# Decimales de cada moneda según ISO 4217 (por defecto 2).
CURRENCY_EXPONENT = {"CLP": 0, "JPY": 0, "KRW": 0, "PYG": 0, "ISK": 0, "VND": 0}


def exponent(currency: str) -> int:
    return CURRENCY_EXPONENT.get(currency.upper(), 2)


def to_minor(amount: str | float | int | None, currency: str) -> int | None:
    """Convierte un monto decimal ("59990", "12.5") a entero en la unidad mínima."""
    if amount is None or amount == "":
        return None
    try:
        value = Decimal(str(amount).strip())
    except InvalidOperation:
        return None
    return int((value * (10 ** exponent(currency))).to_integral_value())


def iter_json_ld(html: str) -> Iterator[dict]:
    """Recorre todos los objetos JSON-LD de la página (aplana listas y @graph)."""
    for match in _LD_RE.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(
                        item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]]
                    )
                yield item


def find_ld_product(html: str) -> dict | None:
    for item in iter_json_ld(html):
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Product" in kinds:
            return item
    return None


def first_offer(product: dict) -> dict | None:
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict) and offers.get("@type") == "AggregateOffer" and "offers" in offers:
        inner = offers["offers"]
        if isinstance(inner, list) and inner:
            return inner[0]
    return offers if isinstance(offers, dict) else None


def availability_in_stock(value: str | None) -> bool:
    """schema.org: InStock / LimitedAvailability / OnlineOnly cuentan como disponibles."""
    if not value:
        return False
    tail = value.rsplit("/", 1)[-1].lower()
    return tail in {"instock", "limitedavailability", "onlineonly", "presale", "preorder"}


def digits_to_int(text: str) -> int | None:
    """ "4.990&nbsp;$" → 4990 (solo para monedas sin decimales, como CLP)."""
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None
