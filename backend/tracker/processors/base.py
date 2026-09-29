"""Interfaz común de los procesadores (uno por tienda, solo en código)."""

from dataclasses import asdict, dataclass, field
from datetime import timedelta


@dataclass(frozen=True)
class ProductRef:
    external_id: str
    canonical_url: str
    variant_id: str = ""


@dataclass
class ScrapeResult:
    title: str
    price: int | None  # unidad mínima de la moneda; None = no se pudo leer
    list_price: int | None
    currency: str  # ISO 4217
    available: bool
    image_url: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Variant:
    url: str
    label: str
    external_id: str
    variant_id: str = ""
    selected: bool = False


@dataclass
class Inspection:
    """Resultado de pedir la página una vez: precio y variantes hermanas."""

    result: ScrapeResult
    variants: list[Variant] = field(default_factory=list)


class FetchError(Exception):
    """Fallo al pedir o interpretar la página (cuenta para el backoff)."""


class NotFoundError(FetchError):
    """El producto no existe (404 o equivalente)."""


class Processor:
    """Clase base. Cada procesador separa `fetch_raw` (red) de `parse` (puro).

    Así los tests corren contra fixtures guardadas sin tocar la red, y el CLI
    `python -m tracker.check` puede guardar la respuesta cruda como fixture.
    """

    name: str = ""
    label: str = ""
    check_interval: timedelta = timedelta(hours=6)
    fixture_ext: str = "html"
    # Caída máxima (%) en una lectura antes de tratarla como anomalía. None = sin
    # límite, para tiendas cuya fuente es estructurada y confiable (una API, no HTML).
    anomaly_drop_pct: int | None = 80
    # True si "sin precio y sin stock" es un agotado real y no un parseo roto (APIs
    # que dejan de listar la oferta cuando se agota). En HTML debe quedar en False.
    sold_out_without_price: bool = False

    # Metadatos para la página "Tiendas soportadas" (solo presentación).
    home_url: str = ""
    example_url: str = ""
    platform: str = ""
    supports_variants: bool = False
    supports_list_price: bool = True  # informa el precio "antes" de una oferta
    slow: bool = False  # pasa por FlareSolverr: la primera lectura tarda
    notes: str = ""

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    def normalize(self, url: str) -> ProductRef:
        raise NotImplementedError

    def domain(self) -> str:
        raise NotImplementedError

    async def fetch_raw(self, ref: ProductRef) -> str:
        raise NotImplementedError

    def parse(self, raw: str, ref: ProductRef) -> ScrapeResult:
        raise NotImplementedError

    def parse_variants(self, raw: str, ref: ProductRef) -> list[Variant]:
        return []

    async def fetch(self, ref: ProductRef) -> ScrapeResult:
        return self.parse(await self.fetch_raw(ref), ref)

    async def inspect(self, ref: ProductRef) -> Inspection:
        raw = await self.fetch_raw(ref)
        return Inspection(self.parse(raw, ref), self.parse_variants(raw, ref))

    async def list_variants(self, ref: ProductRef) -> list[Variant]:
        return self.parse_variants(await self.fetch_raw(ref), ref)
