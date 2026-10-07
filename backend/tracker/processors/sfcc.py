"""Bases para tiendas Salesforce Commerce Cloud (SFCC, ex Demandware).

Lo común: la forma de las URLs de ficha (`…<pid>.html` en un puñado de hosts), los
controladores en `/on/demandware.store/Sites-<sitio>-Site/<locale>/<Controlador>` (sobre
todo `Product-Variation`, que devuelve el producto en JSON) y los atributos de variación
(`dwvar_<pid>_<atributo>=<valor>` en la URL; `variationAttributes` en el JSON).

`SFCCProcessor` solo resuelve URLs (abc y Ahumada leen la ficha HTML a su manera).
`SFCCVariationProcessor` lee `Product-Variation` completo, con selector de tallas y colores
(Hites, Tricot, Bata, Marathon); cada tienda ajusta cómo se leen el precio y el stock.
"""

import json
import re
from datetime import timedelta
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

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

# Nombres de los atributos de variación habituales (algunas tiendas los traen en inglés o
# en minúsculas: "Size", "color").
_ATTR_NAMES = {"color": "Color", "size": "Talla"}


class SFCCProcessor(Processor):
    """Subclases: `name`, `label`, `hosts`, `canonical_host`, `site_id`, `path_re`
    (grupos `slug` y `pid`), `canonical_path` y `fetch_raw`/`parse`."""

    hosts: frozenset[str] = frozenset()
    canonical_host: str = ""
    site_id: str = ""  # "HITES" → Sites-HITES-Site
    locale: str = "default"
    path_re: re.Pattern = re.compile(r"^/(?P<slug>[^/]+?)-(?P<pid>\d{6,})\.html$", re.I)
    # True si el link puede elegir la variante con `dwvar_<pid>_<atributo>` (va en variant_id).
    uses_dwvar: bool = False
    check_interval = timedelta(hours=6)
    platform = "Salesforce Commerce Cloud"

    def _match(self, url: str) -> tuple[re.Match, str] | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme not in ("http", "https") or (parts.hostname or "") not in self.hosts:
            return None
        m = self.path_re.match(parts.path)
        return (m, parts.query) if m else None

    def matches(self, url: str) -> bool:
        return self._match(url) is not None

    def normalize(self, url: str) -> ProductRef:
        found = self._match(url)
        if not found:
            raise ValueError(f"no es una URL de producto de {self.label}")
        m, query = found
        pid = self.pid_from_match(m)
        canonical = f"https://{self.canonical_host}{self.canonical_path(m)}"
        selection = selection_from_query(query, pid) if self.uses_dwvar else {}
        # variant_id es String(128): una selección más larga no es una variante real.
        if not selection or len(encode_selection(selection)) > 128:
            return ProductRef(pid, canonical)
        return ProductRef(
            pid, f"{canonical}?{dwvar_query(pid, selection)}", encode_selection(selection)
        )

    def pid_from_match(self, m: re.Match) -> str:
        return m.group("pid")

    def canonical_path(self, m: re.Match) -> str:
        return f"/{m.group('slug').lower()}-{m.group('pid')}.html"

    def domain(self) -> str:
        return self.canonical_host

    def controller_url(self, controller: str) -> str:
        return (
            f"https://{self.canonical_host}/on/demandware.store/"
            f"Sites-{self.site_id}-Site/{self.locale}/{controller}"
        )

    def check_selection(self, product: dict, ref: ProductRef) -> None:
        """La selección del link debe seguir existiendo en la tienda.

        Con un atributo o valor que no existe, `Product-Variation` no da error: responde el
        maestro sin stock. Sin esta revisión, un valor renombrado o mal escrito se leería
        como "agotado" para siempre en vez de como un seguimiento roto.
        """
        wanted = decode_selection(ref.variant_id)
        if wanted and selected_values(product) != wanted:
            raise FetchError(
                f"la selección {ref.variant_id!r} ya no existe en {self.label} "
                "(algún color o talla cambió de nombre o se quitó)"
            )

    def variation_params(self, ref: ProductRef) -> dict[str, str]:
        """Parámetros de `Product-Variation` para el producto (y variante) de `ref`."""
        params = {"pid": ref.external_id}
        for attr, value in decode_selection(ref.variant_id).items():
            params[f"dwvar_{dwvar_pid(ref.external_id)}_{attr}"] = value
        return params


class SFCCVariationProcessor(SFCCProcessor):
    """Tienda SFCC que se lee con `Product-Variation` (JSON con precio, stock y variaciones).

    El pid del link puede ser una variante (una talla), un grupo de variación (un color, con
    las tallas por elegir) o un maestro, y la selección `dwvar_…` del link va en
    `variant_id`. Sin selección completa, la API responde el grupo o maestro: `available`
    dice si queda stock en alguna talla.

    Un pid inexistente da HTTP 500 en la API (y 404 en la ficha): se confirma con la ficha.
    Subclases: lo de `SFCCProcessor` y, si hace falta, `prices`, `is_available`, `http_get`.
    """

    uses_dwvar = True
    fixture_ext = "json"
    supports_variants = True
    supports_list_price = True
    variants_title = "Color y talla"
    # Parámetros extra que la tienda exige en `Product-Variation`.
    variation_extra: tuple[tuple[str, str], ...] = ()
    # Atributos que el selector deja cambiar (None = todos). En las tiendas donde cada color
    # es su propio grupo de variación, los otros colores del maestro no se pueden elegir.
    variant_attrs: tuple[str, ...] | None = None
    # True: el título lleva la talla o el color elegidos ("Polerón (Talla: M)").
    title_with_selection: bool = False

    async def http_get(self, url: str, params: dict | None = None) -> str:
        return await get_text(url, params=params)

    def variation_params(self, ref: ProductRef) -> dict[str, str]:
        return {**super().variation_params(ref), **dict(self.variation_extra)}

    async def fetch_raw(self, ref: ProductRef) -> str:
        url = self.controller_url("Product-Variation")
        try:
            return await self.http_get(url, params=self.variation_params(ref))
        except NotFoundError:
            raise
        except FetchError:
            await self.http_get(ref.canonical_url)  # 404 → NotFoundError
            raise

    def product(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError(f"{self.label} no devolvió JSON") from exc
        product = data.get("product") if isinstance(data, dict) else None
        if not isinstance(product, dict) or not product.get("id"):
            raise FetchError(f"la respuesta de {self.label} no trae el producto")
        return product

    def prices(self, product: dict) -> tuple[int | None, int | None, str]:
        """(precio, precio normal tachado, moneda) de `product.price` (`sales` / `list`)."""
        prices = product.get("price") or {}
        sales = prices.get("sales") or {}
        currency = sales.get("currency") or "CLP"
        price = to_minor(sales.get("value"), currency)
        normal = to_minor((prices.get("list") or {}).get("value"), currency)
        return price, list_price_if_higher(normal, price), currency

    def is_available(self, product: dict) -> bool:
        return product.get("available") is True

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        product = self.product(raw)
        self.check_selection(product, ref)
        price, list_price, currency = self.prices(product)
        title = (product.get("productName") or "").strip()
        if self.title_with_selection:
            chosen = self.selection_label(product)
            if chosen:
                title = f"{title} ({chosen})"
        return ScrapeResult(
            title=title,
            price=price,
            list_price=list_price,
            currency=currency,
            available=self.is_available(product),
            image_url=_image(product),
        )

    def can_change(self, attr: dict) -> bool:
        return self.variant_attrs is None or attr["id"] in self.variant_attrs

    def label_names(self, attrs: list[dict]) -> dict[str, str]:
        """{atributo: nombre} de los que van en las etiquetas: los que el selector puede
        cambiar y tienen más de un valor (el color único de un grupo no aporta)."""
        names = {
            a["id"]: attr_name(a) for a in attrs if len(a["values"]) > 1 and self.can_change(a)
        }
        return names or {a["id"]: attr_name(a) for a in attrs}

    def selection_label(self, product: dict) -> str:
        """Etiqueta de la selección ("Talla: M"); vacía si falta elegir algo."""
        attrs = variation_attributes(product)
        current = selected_values(product)
        if not attrs or set(current) != {a["id"] for a in attrs}:
            return ""
        shown = {
            a["id"]: v.get("displayValue") or v["id"]
            for a in attrs
            for v in a["values"]
            if v.get("id") == current[a["id"]]
        }
        return ", ".join(
            f"{n}: {shown.get(a, current[a])}" for a, n in self.label_names(attrs).items()
        )

    def master_id(self, product: dict) -> str | None:
        """Pid al que se refieren los `dwvar_` de la ficha: el de `selectedProductUrl`."""
        m = self.path_re.match(unquote(urlsplit(product.get("selectedProductUrl") or "").path))
        return self.pid_from_match(m) if m else None

    def master_url(self, product: dict, ref: ProductRef, master: str) -> str | None:
        """URL canónica (sin query) del maestro o grupo, para armar los links del selector."""
        for url in (product.get("selectedProductUrl") or "", ref.canonical_url):
            m = self.path_re.match(unquote(urlsplit(url).path))
            if m and self.pid_from_match(m) == master:
                return f"https://{self.canonical_host}{self.canonical_path(m)}"
        return None

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        """Variantes a un paso de la actual, sin pedir nada más a la tienda.

        `variationAttributes` trae, para cada atributo, sus valores y si se pueden elegir
        con el resto de la selección actual. Con la selección completa se ofrece cambiar un
        atributo a la vez (los otros colores en la misma talla y las otras tallas del mismo
        color). Si falta elegir un atributo (lo normal: el link de un color sin talla), se
        ofrece seguir "cualquier talla" (el link tal cual) o cada talla.
        """
        product = self.product(raw)
        attrs = variation_attributes(product)
        current = selected_values(product)
        master = self.master_id(product)
        base = self.master_url(product, ref, master) if master else None
        if not base or not attrs:
            return []
        names = self.label_names(attrs)
        shown = {
            (a["id"], v["id"]): v.get("displayValue") or v["id"]
            for a in attrs
            for v in a["values"]
            if v.get("id")
        }

        def label(combo: dict[str, str], unavailable: bool) -> str:
            text = ", ".join(
                f"{names[a]}: {shown.get((a, combo[a]), combo[a])}" for a in names if a in combo
            )
            return f"{text} (no disponible)" if unavailable else text

        def url(combo: dict[str, str]) -> str:
            return f"{base}?{dwvar_query(master, combo)}"

        available = self.is_available(product)
        missing = [a for a in attrs if a["id"] not in current]
        if len(missing) == 1 and self.can_change(missing[0]):
            attr = missing[0]
            any_label = f"Cualquier {attr_name(attr).lower()}"
            out = [
                Variant(
                    ref.canonical_url,
                    any_label if available else f"{any_label} (no disponible)",
                    ref.external_id,
                    ref.variant_id,
                    selected=True,
                )
            ]
            for value in attr["values"]:
                if value.get("id"):
                    combo = {**current, attr["id"]: value["id"]}
                    out.append(
                        Variant(
                            url(combo),
                            label(combo, value.get("selectable") is False),
                            master,
                            encode_selection(combo),
                        )
                    )
            return out if len(out) > 2 else []
        if missing:
            return []

        # Un maestro sin selección sigue la variante por defecto, que puede cambiar: en
        # el selector se ofrece la combinación explícita.
        here = encode_selection(current)
        explicit = ref.external_id == master and not ref.variant_id
        out = [
            Variant(
                url(current) if explicit else ref.canonical_url,
                label(current, not available),
                master if explicit else ref.external_id,
                here if explicit else ref.variant_id,
                selected=True,
            )
        ]
        seen = {here}
        for attr in attrs:
            if len(attr["values"]) < 2 or not self.can_change(attr):
                continue
            for value in attr["values"]:
                if not value.get("id"):
                    continue
                combo = {**current, attr["id"]: value["id"]}
                key = encode_selection(combo)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Variant(
                        url=url(combo),
                        label=label(combo, value.get("selectable") is False),
                        external_id=master,
                        variant_id=key,
                    )
                )
        return out if len(out) > 1 else []


def dwvar_pid(pid: str) -> str:
    """Pid como va en `dwvar_<pid>_<atributo>`: SFCC duplica los `_` del pid
    (`701M_2024_9136031` → `dwvar_701M__2024__9136031_size`) para poder separarlo del
    atributo."""
    return pid.replace("_", "__")


def selection_from_query(query: str, pid: str) -> dict[str, str]:
    """`dwvar_<pid>_<atributo>=<valor>` de la URL → {atributo: valor} (vacíos fuera)."""
    prefix = f"dwvar_{dwvar_pid(pid)}_"
    return {
        key[len(prefix) :]: value.strip()
        for key, value in parse_qsl(query)
        if key.startswith(prefix) and len(key) > len(prefix) and value.strip()
    }


def encode_selection(selection: dict[str, str]) -> str:
    """{atributo: valor} → "atributo=valor&…" ordenado (forma estable para variant_id)."""
    return urlencode(sorted(selection.items()))


def decode_selection(variant_id: str) -> dict[str, str]:
    return dict(parse_qsl(variant_id)) if variant_id else {}


def dwvar_query(pid: str, selection: dict[str, str]) -> str:
    return urlencode(sorted((f"dwvar_{dwvar_pid(pid)}_{a}", v) for a, v in selection.items()))


def variation_attributes(product: dict) -> list[dict]:
    """`variationAttributes` del JSON de `Product-Variation`, solo los bien formados."""
    return [
        attr
        for attr in product.get("variationAttributes") or []
        if isinstance(attr, dict) and attr.get("id") and isinstance(attr.get("values"), list)
    ]


def selected_values(product: dict) -> dict[str, str]:
    """{atributo: valor elegido} según `variationAttributes` (los sin elegir no aparecen)."""
    out = {}
    for attr in variation_attributes(product):
        for value in attr["values"]:
            if value.get("selected") and value.get("id"):
                out[attr["id"]] = value["id"]
    return out


def attr_name(attr: dict) -> str:
    return _ATTR_NAMES.get(str(attr["id"]).lower()) or attr.get("displayName") or attr["id"]


def list_price_if_higher(normal: int | None, price: int | None) -> int | None:
    """El precio normal solo cuenta si es mayor que el precio (si no, no hay oferta)."""
    return normal if normal and price is not None and normal > price else None


def _image(product: dict) -> str | None:
    large = (product.get("images") or {}).get("large") or []
    first = large[0] if large and isinstance(large[0], dict) else {}
    url = first.get("url") or first.get("absURL")
    return url if isinstance(url, str) and url.startswith("http") else None
