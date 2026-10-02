"""Registro de procesadores. Para agregar una tienda: una clase aquí y sus fixtures."""

from tracker.processors.base import (
    FetchError,
    Inspection,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.dementegames import DementeGamesProcessor
from tracker.processors.entrejuegos import EntrejuegosProcessor
from tracker.processors.falabella import FalabellaProcessor
from tracker.processors.hites import HitesProcessor
from tracker.processors.ikea import IkeaProcessor
from tracker.processors.jumbo import JumboProcessor
from tracker.processors.lafortaleza import LaFortalezaProcessor
from tracker.processors.lider import LiderProcessor
from tracker.processors.mercadolibre import MercadoLibreProcessor
from tracker.processors.pcfactory import PcFactoryProcessor
from tracker.processors.santaisabel import SantaIsabelProcessor
from tracker.processors.sodimac import SodimacProcessor
from tracker.processors.solotodo import SolotodoProcessor
from tracker.processors.steam import SteamProcessor
from tracker.processors.tottus import TottusProcessor

PROCESSORS: dict[str, Processor] = {
    p.name: p
    for p in (
        SteamProcessor(),
        IkeaProcessor(),
        EntrejuegosProcessor(),
        DementeGamesProcessor(),
        LaFortalezaProcessor(),
        MercadoLibreProcessor(),
        LiderProcessor(),
        JumboProcessor(),
        SantaIsabelProcessor(),
        PcFactoryProcessor(),
        FalabellaProcessor(),
        HitesProcessor(),
        SolotodoProcessor(),
        SodimacProcessor(),
        TottusProcessor(),
    )
}


def get_processor(name: str) -> Processor:
    return PROCESSORS[name]


def find_processor(url: str) -> Processor | None:
    for proc in PROCESSORS.values():
        if proc.matches(url):
            return proc
    return None


__all__ = [
    "PROCESSORS",
    "FetchError",
    "Inspection",
    "NotFoundError",
    "Processor",
    "ProductRef",
    "ScrapeResult",
    "Variant",
    "find_processor",
    "get_processor",
]
