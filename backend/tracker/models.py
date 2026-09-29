"""Modelo de datos (ver plan.md, sección "Modelo de datos")."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from tracker.db import utcnow


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}  # noqa: RUF012


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    # Nulo hasta que el usuario usa su invitación.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_quota: Mapped[int] = mapped_column(Integer, default=50)
    # Preferencias de la UI por usuario (tema, paleta): ver api/auth.py.
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    watches: Mapped[list["Watch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    channels: Mapped[list["Channel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # telegram | discord
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="channels")


class TelegramLinkCode(Base):
    """Código de un solo uso para el deep link t.me/<bot>?start=<código>."""

    __tablename__ = "telegram_link_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("processor", "external_id", "variant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    processor: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    # Cadena vacía cuando no hay variante: en SQLite los NULL no chocan en un UNIQUE.
    variant_id: Mapped[str] = mapped_column(String(128), default="")
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="CLP")
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | broken
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_check_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_manual_check_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    price_points: Mapped[list["PricePoint"]] = relationship(
        back_populates="product",
        order_by="PricePoint.checked_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    watches: Mapped[list["Watch"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    price: Mapped[int | None] = mapped_column(Integer)
    list_price: Mapped[int | None] = mapped_column(Integer)
    available: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    product: Mapped[Product] = relationship(back_populates="price_points")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # price_none | big_drop
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    product: Mapped[Product] = relationship()


class Watch(Base):
    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    price_at_start: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="watches")
    product: Mapped[Product] = relationship(back_populates="watches")
    rules: Mapped[list["AlertRule"]] = relationship(
        back_populates="watch", cascade="all, delete-orphan", order_by="AlertRule.id"
    )
    channel_overrides: Mapped[list["WatchChannel"]] = relationship(cascade="all, delete-orphan")


class WatchChannel(Base):
    """Override por Watch: permite apagar un canal global solo para este Watch."""

    __tablename__ = "watch_channels"

    watch_id: Mapped[int] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    state: Mapped[dict[str, Any]] = mapped_column(default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    watch: Mapped[Watch] = relationship(back_populates="rules")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    delivery: Mapped[dict[str, Any]] = mapped_column(default=dict)

    watch: Mapped[Watch] = relationship()


class OAuthToken(Base):
    """Token OAuth de un proveedor (hoy solo MercadoLibre), uno por proveedor.

    El refresh token de MercadoLibre es de un solo uso: cada renovación trae uno
    nuevo que reemplaza al anterior.
    """

    __tablename__ = "oauth_tokens"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    account_id: Mapped[str] = mapped_column(String(64), default="")
    scope: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StoreLogo(Base):
    """Logo de una tienda subido por el admin; reemplaza al de `processors/logos/`."""

    __tablename__ = "store_logos"

    processor: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
