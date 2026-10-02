"""Entorno de Alembic: usa el motor de tracker.db (SQLite en WAL)."""

from logging.config import fileConfig

from alembic import context
from tracker import db
from tracker.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(db.engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with db.engine.connect() as connection:
        # FK apagadas durante las migraciones: recrear una tabla con hijos (DROP + RENAME)
        # los borraría en cascada. Dentro de una transacción el PRAGMA no tiene efecto,
        # por eso va antes. Cada migración que recrea revisa `PRAGMA foreign_key_check`.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            # render_as_batch: SQLite no soporta ALTER TABLE completo.
            context.configure(
                connection=connection, target_metadata=target_metadata, render_as_batch=True
            )
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            # La conexión vuelve al pool: que no quede sin FK para quien la reuse.
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
