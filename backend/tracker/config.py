"""Configuración leída del entorno (backend/.env en producción)."""

import os
from dataclasses import dataclass, field


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get("DATABASE_URL", "sqlite:///./data/tracker.db")
    )
    # Se usa como clave HMAC para guardar hashes de tokens (sesiones, invitaciones).
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", "dev-inseguro"))
    public_url: str = field(
        default_factory=lambda: os.environ.get("PUBLIC_URL", "http://localhost:5173").rstrip("/")
    )
    cookie_secure: bool = field(
        default_factory=lambda: _bool(os.environ.get("COOKIE_SECURE"), True)
    )
    scheduler_enabled: bool = field(
        default_factory=lambda: _bool(os.environ.get("SCHEDULER_ENABLED"), True)
    )
    telegram_bot_token: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    )
    flaresolverr_url: str = field(
        default_factory=lambda: os.environ.get("FLARESOLVERR_URL", "http://localhost:8191/v1")
    )
    # Sesión persistente de FlareSolverr (reutiliza la cookie de Cloudflare).
    flaresolverr_session: str = field(
        default_factory=lambda: os.environ.get("FLARESOLVERR_SESSION", "price_tracker")
    )
    # MercadoLibre (OAuth, ver tracker/meli.py). Sin client id/secret, el procesador
    # queda deshabilitado y el panel admin lo muestra como "no configurado".
    meli_client_id: str = field(
        default_factory=lambda: os.environ.get("MELI_CLIENT_ID", "").strip()
    )
    meli_client_secret: str = field(
        default_factory=lambda: os.environ.get("MELI_CLIENT_SECRET", "").strip()
    )
    # Vacío = f"{PUBLIC_URL}/api/admin/meli/callback". Debe coincidir exacto con la
    # redirect URI registrada en la app de MercadoLibre.
    meli_redirect_uri: str = field(default_factory=lambda: os.environ.get("MELI_REDIRECT_URI", ""))
    # Segundos mínimos entre dos peticiones al mismo dominio.
    domain_min_interval: float = field(
        default_factory=lambda: float(os.environ.get("DOMAIN_MIN_INTERVAL", "5"))
    )
    session_days: int = 30
    invite_hours: int = 48
    manual_check_cooldown_min: int = 15

    def __post_init__(self) -> None:
        if not self.meli_redirect_uri:
            self.meli_redirect_uri = f"{self.public_url}/api/admin/meli/callback"


settings = Settings()
