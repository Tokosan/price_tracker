from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from tracker import db as dbmod
from tracker.models import Base


def test_migraciones_coinciden_con_los_modelos(tmp_path):
    dbmod.configure(f"sqlite:///{tmp_path}/mig.db")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{tmp_path}/mig.db")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_migrar_no_borra_datos(tmp_path):
    """Una migración que recrea una tabla (batch en SQLite) borra en cascada sus hijos."""
    url = f"sqlite:///{tmp_path}/datos.db"
    dbmod.configure(url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0002")
    with dbmod.engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (id, username, role, active, watch_quota, created_at)"
            " VALUES (1, 'ana', 'user', 1, 50, '2026-01-01')"
        )
        conn.exec_driver_sql(
            "INSERT INTO products (id, processor, external_id, variant_id, canonical_url, title,"
            " currency, status, fail_count, next_check_at, created_at)"
            " VALUES (1, 'steam', '1', '', 'https://x', 'Juego', 'CLP', 'ok', 0,"
            " '2026-01-01', '2026-01-01')"
        )
        conn.exec_driver_sql(
            "INSERT INTO watches (id, user_id, product_id, active, created_at)"
            " VALUES (1, 1, 1, 1, '2026-01-01')"
        )
    command.upgrade(cfg, "head")
    with dbmod.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM watches").scalar() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM users").scalar() == 1
