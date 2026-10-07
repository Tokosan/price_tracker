"""Procesador de Decathlon Chile (www.decathlon.cl, plataforma propia en Next.js).

Cloudflare bloquea el fingerprint TLS de httpx (403): se pide con curl_cffi imitando a
Chrome. La ficha es de Next.js con App Router: no hay `__NEXT_DATA__`, los datos van en
el payload de React Server Components (`self.__next_f.push([1, "<texto>"])`). Al juntar
esos textos aparece el objeto `"itemGroup": {...}` (JSON válido), que trae:

- `skuGroups[]`: un grupo por color (modelo), con `modelId`, `modelUrl`, `isAvailable` y
  `skus[]` (una por talla): `skuId` (UUID), `sizeGridValue`/`sizeLabel`, `colors`,
  `isAvailable` y `offers[].fixedPrices[].typeTargets[]` con `priceType` (`STANDARD`,
  `END_OF_LINE`…), vigencia (`start`/`end`) y `currencies.main.valueWithTaxes` (precio) y
  `referenceValueWithTaxes` (precio tachado, solo con descuento).
- Una talla agotada sigue listada con `isAvailable: false` (tag `TEMPORARY_OUT_OF_STOCK`);
  las tallas de fin de temporada agotadas desaparecen de la lista.

El JSON-LD de la ficha (`ProductGroup` + `Product/Offer`) solo trae el precio del modelo y
su stock, sin tallas: no se usa.

URL: `/p/<slug>/<itemGroup>/<variance>`, donde `<variance>` = `c<color>…m<modelId>` (o solo
`m<modelId>`). Un `modelId` que no existe en el grupo redirige (200) al modelo por defecto,
así que `parse` busca el modelo pedido entre los colores del grupo. `external_id` = modelId
(cada color es su propio producto) y `variant_id` = `skuId` de la talla, que va en la URL
como `?sku=<uuid>` (Decathlon lo ignora). Sin talla se sigue "cualquier talla": el precio
más bajo entre las tallas con stock.
"""

import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from tracker.processors.base import (
    FetchError,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.http import get_text_impersonate
from tracker.processors.util import to_minor

_HOST = "www.decathlon.cl"
_URL_RE = re.compile(
    r"^https?://(?:www\.)?decathlon\.cl/p/([^/?#]+)/(\d+)/((?:c\d+)*m(\d+))/?(?:[?#].*)?$",
    re.I,
)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
_ITEM_GROUP = '"itemGroup":{'


class DecathlonProcessor(Processor):
    name = "decathlon"
    label = "Decathlon"
    home_url = "https://www.decathlon.cl/"
    example_url = "https://www.decathlon.cl/p/kit-mancuernas-20-kg/7449/c1m8018574"
    platform = "Next.js (plataforma propia)"
    supports_variants = True
    supports_list_price = True
    sold_out_without_price = True  # una talla que desaparece de la ficha es un agotado
    variants_title = "¿Qué color o talla seguir?"
    variants_hint = (
        "Cada color es un producto distinto. Dentro de un color puedes seguir cualquier "
        "talla (el precio más bajo, con stock en alguna) o tallas puntuales."
    )
    notes = (
        'Precio de la ficha; el "antes" es el precio tachado de las ofertas. Cada color se '
        "sigue por separado. Sin elegir talla se sigue el precio más bajo entre las tallas "
        "con stock; una talla puntual se sigue con su propio precio y stock."
    )

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url.strip()))

    def normalize(self, url: str) -> ProductRef:
        url = url.strip()
        m = _URL_RE.match(url)
        if not m:
            raise ValueError("no es una URL de producto de Decathlon")
        slug, group, variance, model = m.group(1).lower(), m.group(2), m.group(3), m.group(4)
        sku = (parse_qs(urlsplit(url).query).get("sku") or [""])[0].strip().lower()
        sku = sku if _UUID_RE.match(sku) else ""
        return ProductRef(model, _url(f"/p/{slug}/{group}/{variance.lower()}", sku), sku)

    def domain(self) -> str:
        return _HOST

    async def fetch_raw(self, ref: ProductRef) -> str:
        return await get_text_impersonate(ref.canonical_url.split("?", 1)[0])

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        item_group = _item_group(raw)
        group = _model(item_group, ref.external_id)
        skus = [s for s in group.get("skus") or [] if isinstance(s, dict)]
        if not skus:
            raise FetchError("el modelo no trae tallas (skus)")
        item_group_title = _title(skus[0])
        details = [_colors(group)] if len(item_group.get("skuGroups") or []) > 1 else []
        if ref.variant_id:
            sku = next((s for s in skus if s.get("skuId") == ref.variant_id), None)
            if sku is None:
                # Fin de temporada: la talla agotada deja de listarse.
                title = _with_details(item_group_title, details)
                return ScrapeResult(title, None, None, "CLP", False, _image(skus[0]))
            size = _size(sku)
            if size:
                details.append(f"talla {size}")
            chosen, available = sku, sku.get("isAvailable") is True
        else:
            in_stock = [s for s in skus if s.get("isAvailable") is True]
            available = bool(in_stock)
            chosen = min(in_stock or skus, key=lambda s: _prices(s)[0] or 10**15)
        price, list_price = _prices(chosen)
        if price is None:
            raise FetchError("la talla no trae precio")
        title = _with_details(item_group_title, details)
        return ScrapeResult(title, price, list_price, "CLP", available, _image(chosen))

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Las tallas del color actual ("cualquier talla" + cada una) y los otros colores."""
        item_group = _item_group(raw)
        current = _model(item_group, ref.external_id)
        base = ref.canonical_url.split("?", 1)[0]
        out: list[Variant] = []
        skus = [s for s in current.get("skus") or [] if _UUID_RE.match(str(s.get("skuId")))]
        if len(skus) > 1:
            out.append(
                Variant(
                    base,
                    _group_label(current, "Cualquier talla"),
                    ref.external_id,
                    "",
                    selected=not ref.variant_id,
                )
            )
            for s in skus:
                price, _ = _prices(s)
                label = f"Talla {_size(s) or s['skuId']}"
                if price is not None:
                    label += f": {_money(price)}"
                if s.get("isAvailable") is not True:
                    label += " (agotada)"
                out.append(
                    Variant(
                        _url(urlsplit(base).path, s["skuId"]),
                        label,
                        ref.external_id,
                        s["skuId"],
                        selected=s["skuId"] == ref.variant_id,
                    )
                )
        others = [
            g
            for g in item_group.get("skuGroups") or []
            if str(g.get("modelId")) != ref.external_id and _valid_model_path(g.get("modelUrl"))
        ]
        if others and not out:
            out.append(Variant(base, _group_label(current), ref.external_id, "", True))
        for g in others:
            out.append(
                Variant(
                    _url(g["modelUrl"]),
                    _group_label(g),
                    str(g["modelId"]),
                    "",
                    selected=False,
                )
            )
        return sorted(out, key=lambda v: not v.selected)


def _valid_model_path(path) -> bool:
    return isinstance(path, str) and bool(_URL_RE.match(f"https://{_HOST}{path}"))


def _url(path: str, sku: str = "") -> str:
    url = f"https://{_HOST}{path}"
    return f"{url}?sku={sku}" if sku else url


def flight(raw: str) -> str:
    """El texto del payload RSC: la concatenación de los `self.__next_f.push([1, …])`."""
    parts = []
    for m in _PUSH_RE.finditer(raw):
        try:
            chunk = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and chunk[0] == 1:
            parts.append(str(chunk[1]))
    return "".join(parts)


def _item_group(raw: str) -> dict:
    text = flight(raw)
    if not text:
        raise FetchError("la página de Decathlon no trae el payload de Next.js")
    decoder = json.JSONDecoder()
    start = text.find(_ITEM_GROUP)
    while start >= 0:
        try:
            obj, _ = decoder.raw_decode(text, start + len(_ITEM_GROUP) - 1)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("skuGroups"), list):
            return obj
        start = text.find(_ITEM_GROUP, start + 1)
    # Categorías, búsquedas y páginas de contenido no traen el itemGroup.
    raise NotFoundError("no es una ficha de producto de Decathlon")


def _model(item_group: dict, model_id: str) -> dict:
    for g in item_group.get("skuGroups") or []:
        if isinstance(g, dict) and str(g.get("modelId")) == model_id:
            return g
    # Un modelId que ya no existe redirige al modelo por defecto del grupo.
    raise NotFoundError(f"el modelo {model_id} ya no está en la ficha de Decathlon")


def _prices(sku: dict) -> tuple[int | None, int | None]:
    """(precio, tachado) vigentes de la primera oferta de la talla."""
    now = datetime.now(UTC)
    candidates: list[tuple[datetime, dict]] = []
    for offer in sku.get("offers") or []:
        for fixed in offer.get("fixedPrices") or []:
            for target in fixed.get("typeTargets") or []:
                main = (target.get("currencies") or {}).get("main") or {}
                if main.get("currency") not in (None, "CLP"):
                    continue
                start, end = _date(target.get("start")), _date(target.get("end"))
                if (start and start > now) or (end and end <= now):
                    continue
                candidates.append((start or datetime.min.replace(tzinfo=UTC), main))
        if candidates:
            break  # la primera oferta (Decathlon); las demás serían de otros vendedores
    if not candidates:
        return None, None
    main = max(candidates, key=lambda c: c[0])[1]  # la vigente más reciente
    price = to_minor(main.get("valueWithTaxes"), "CLP")
    reference = to_minor(_number(main.get("referenceValueWithTaxes")), "CLP")
    if not price:
        return None, None
    return price, reference if reference and reference > price else None


def _number(value):
    return value if isinstance(value, int | float) else None


def _date(value) -> datetime | None:
    if not isinstance(value, str) or not value[:1].isdigit():
        return None  # "$undefined"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _title(sku: dict) -> str:
    return " ".join(str(sku.get("title") or "").split())


def _with_details(title: str, details: list[str]) -> str:
    details = [d for d in details if d]
    return f"{title} ({', '.join(details)})" if details else title


def _size(sku: dict) -> str:
    """Talla legible ("M", "39"); vacío si es talla única."""
    size = str(sku.get("sizeGridValue") or sku.get("sizeLabel") or "").strip().rstrip(".")
    if not size.strip("."):
        return ""
    for group in sku.get("sizeGroups") or []:
        if str(group.get("name") or "").lower() == "talla única":
            return ""
    return size


def _colors(group: dict) -> str:
    colors = ((group.get("varianceAttributes") or {}).get("colors")) or []
    names = [str(c.get("name") or "").strip() for c in colors if isinstance(c, dict)]
    return " / ".join(n for n in names if n and n != "-")


def _group_label(group: dict, prefix: str = "") -> str:
    color = _colors(group) or f"modelo {group.get('modelId')}"
    skus = group.get("skus") or []
    prices = [p for p in (_prices(s)[0] for s in skus) if p is not None]
    label = f"{prefix} ({color})" if prefix else f"Color {color}"
    if prices:
        label += f": desde {_money(min(prices))}"
    if group.get("isAvailable") is False:
        label += " (agotado)"
    return label


def _image(sku: dict) -> str | None:
    url = (sku.get("mainImage") or {}).get("url")
    return url if isinstance(url, str) and url.startswith("http") else None


def _money(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")
