"""Base chica para tiendas Salesforce Commerce Cloud (SFCC, ex Demandware): Hites, abc.

Lo común es poco: la forma de las URLs de ficha (`…<pid>.html` en un puñado de hosts),
los controladores en `/on/demandware.store/Sites-<sitio>-Site/<locale>/<Controlador>`
(sobre todo `Product-Variation`, que devuelve el producto en JSON) y los atributos de
variación (`dwvar_<pid>_<atributo>=<valor>` en la URL; `variationAttributes` en el JSON).
Cómo se lee el precio es propio de cada tienda.
"""

import re
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit

from tracker.processors.base import FetchError, Processor, ProductRef


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
        pid = m.group("pid")
        canonical = f"https://{self.canonical_host}{self.canonical_path(m)}"
        selection = selection_from_query(query, pid) if self.uses_dwvar else {}
        # variant_id es String(128): una selección más larga no es una variante real.
        if not selection or len(encode_selection(selection)) > 128:
            return ProductRef(pid, canonical)
        return ProductRef(
            pid, f"{canonical}?{dwvar_query(pid, selection)}", encode_selection(selection)
        )

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
            params[f"dwvar_{ref.external_id}_{attr}"] = value
        return params


def selection_from_query(query: str, pid: str) -> dict[str, str]:
    """`dwvar_<pid>_<atributo>=<valor>` de la URL → {atributo: valor} (vacíos fuera)."""
    prefix = f"dwvar_{pid}_"
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
    return urlencode(sorted((f"dwvar_{pid}_{a}", v) for a, v in selection.items()))


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
