"""Logos de las tiendas: uno por defecto en el código y un reemplazo opcional del admin.

Los de por defecto viven en `processors/logos/<procesador>.png`; el que sube el admin
se guarda en la tabla `store_logos` y tiene prioridad. Solo PNG (se valida la firma y
el tamaño leyendo la cabecera, sin dependencias de imágenes).
"""

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from tracker.db import utcnow
from tracker.models import StoreLogo

DEFAULTS_DIR = Path(__file__).parent / "processors" / "logos"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 512 * 1024
MIN_SIDE, MAX_SIDE = 16, 1024


class LogoError(ValueError):
    """El archivo no es un PNG aceptable."""


@dataclass
class Logo:
    data: bytes
    etag: str
    custom: bool


def _etag(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def validate_png(data: bytes) -> tuple[int, int]:
    """Devuelve (ancho, alto) o lanza LogoError."""
    if len(data) > MAX_BYTES:
        raise LogoError(f"el logo no puede pesar más de {MAX_BYTES // 1024} KB")
    # Firma (8 bytes) + largo del chunk (4) + "IHDR" (4) + ancho y alto (4 + 4).
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise LogoError("el logo debe ser un PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise LogoError(f"el logo debe medir entre {MIN_SIDE} y {MAX_SIDE} px por lado")
    return width, height


def default_logo(name: str) -> bytes | None:
    path = DEFAULTS_DIR / f"{name}.png"
    return path.read_bytes() if path.is_file() else None


def get_logo(db: DbSession, name: str) -> Logo | None:
    row = db.get(StoreLogo, name)
    if row is not None:
        return Logo(row.data, row.sha256[:16], custom=True)
    data = default_logo(name)
    return Logo(data, _etag(data), custom=False) if data else None


def logo_url(logo: Logo | None, name: str) -> str | None:
    # La versión en la URL permite cachear el logo sin fecha de vencimiento.
    return f"/api/processors/{name}/logo?v={logo.etag}" if logo else None


def set_logo(db: DbSession, name: str, data: bytes) -> Logo:
    validate_png(data)
    sha = hashlib.sha256(data).hexdigest()
    row = db.get(StoreLogo, name)
    if row is None:
        db.add(StoreLogo(processor=name, data=data, sha256=sha, updated_at=utcnow()))
    else:
        row.data, row.sha256, row.updated_at = data, sha, utcnow()
    db.commit()
    return Logo(data, sha[:16], custom=True)


def reset_logo(db: DbSession, name: str) -> None:
    row = db.get(StoreLogo, name)
    if row is not None:
        db.delete(row)
        db.commit()
