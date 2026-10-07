"""Registro de procesadores. Para agregar una tienda: una clase aquí y sus fixtures."""

from tracker.processors.abc import AbcProcessor
from tracker.processors.ahumada import AhumadaProcessor
from tracker.processors.antartica import AntarticaProcessor
from tracker.processors.bamers import BamersProcessor
from tracker.processors.base import (
    FetchError,
    Inspection,
    NotFoundError,
    Processor,
    ProductRef,
    ScrapeResult,
    Variant,
)
from tracker.processors.bsoul import BSoulProcessor
from tracker.processors.buscalibre import BuscalibreProcessor
from tracker.processors.columbia import ColumbiaProcessor
from tracker.processors.contrapunto import ContrapuntoProcessor
from tracker.processors.crocs import CrocsProcessor
from tracker.processors.cruzverde import CruzVerdeProcessor
from tracker.processors.dementegames import DementeGamesProcessor
from tracker.processors.dockers import DockersProcessor
from tracker.processors.doite import DoiteProcessor
from tracker.processors.drmartens import DrMartensProcessor
from tracker.processors.drsimi import DrSimiProcessor
from tracker.processors.easy import EasyProcessor
from tracker.processors.ecofarmacias import EcofarmaciasProcessor
from tracker.processors.entrejuegos import EntrejuegosProcessor
from tracker.processors.falabella import FalabellaProcessor
from tracker.processors.fashionspark import FashionsParkProcessor
from tracker.processors.feriachilenadellibro import FeriaChilenaDelLibroProcessor
from tracker.processors.gatoarcano import GatoArcanoProcessor
from tracker.processors.gotta import GottaProcessor
from tracker.processors.hites import HitesProcessor
from tracker.processors.hushpuppies import HushPuppiesProcessor
from tracker.processors.ikea import IkeaProcessor
from tracker.processors.jockey import JockeyProcessor
from tracker.processors.jumbo import JumboProcessor
from tracker.processors.kayser import KayserProcessor
from tracker.processors.lafortaleza import LaFortalezaProcessor
from tracker.processors.lider import LiderProcessor
from tracker.processors.ligafarmacia import LigaFarmaciaProcessor
from tracker.processors.lippi import LippiProcessor
from tracker.processors.mercadolibre import MercadoLibreProcessor
from tracker.processors.merrell import MerrellProcessor
from tracker.processors.paris import ParisProcessor
from tracker.processors.patagonia import PatagoniaProcessor
from tracker.processors.pcfactory import PcFactoryProcessor
from tracker.processors.piedrabruja import PiedraBrujaProcessor
from tracker.processors.preunic import PreunicProcessor
from tracker.processors.ripley import RipleyProcessor
from tracker.processors.rockford import RockfordProcessor
from tracker.processors.salcobrand import SalcobrandProcessor
from tracker.processors.salomon import SalomonProcessor
from tracker.processors.santaisabel import SantaIsabelProcessor
from tracker.processors.sodimac import SodimacProcessor
from tracker.processors.solotodo import SolotodoProcessor
from tracker.processors.spdigital import SpDigitalProcessor
from tracker.processors.steam import SteamProcessor
from tracker.processors.streetmachine import StreetMachineProcessor
from tracker.processors.tottus import TottusProcessor
from tracker.processors.underarmour import UnderArmourProcessor
from tracker.processors.unimarc import UnimarcProcessor
from tracker.processors.vans import VansProcessor
from tracker.processors.vudugaming import VuduGamingProcessor
from tracker.processors.wrangler import WranglerProcessor

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
        EasyProcessor(),
        PcFactoryProcessor(),
        FalabellaProcessor(),
        HitesProcessor(),
        SolotodoProcessor(),
        SodimacProcessor(),
        TottusProcessor(),
        AbcProcessor(),
        ParisProcessor(),
        RipleyProcessor(),
        UnimarcProcessor(),
        SpDigitalProcessor(),
        EcofarmaciasProcessor(),
        CruzVerdeProcessor(),
        SalcobrandProcessor(),
        DrSimiProcessor(),
        AhumadaProcessor(),
        GatoArcanoProcessor(),
        AntarticaProcessor(),
        PiedraBrujaProcessor(),
        ContrapuntoProcessor(),
        FeriaChilenaDelLibroProcessor(),
        BuscalibreProcessor(),
        PreunicProcessor(),
        VuduGamingProcessor(),
        LigaFarmaciaProcessor(),
        LippiProcessor(),
        UnderArmourProcessor(),
        PatagoniaProcessor(),
        DoiteProcessor(),
        MerrellProcessor(),
        VansProcessor(),
        SalomonProcessor(),
        ColumbiaProcessor(),
        RockfordProcessor(),
        HushPuppiesProcessor(),
        CrocsProcessor(),
        DrMartensProcessor(),
        WranglerProcessor(),
        DockersProcessor(),
        JockeyProcessor(),
        KayserProcessor(),
        FashionsParkProcessor(),
        StreetMachineProcessor(),
        BamersProcessor(),
        GottaProcessor(),
        BSoulProcessor(),
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
