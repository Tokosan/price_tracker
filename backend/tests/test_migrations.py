import json

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
        conn.exec_driver_sql(
            "INSERT INTO price_points (product_id, price, available, checked_at)"
            " VALUES (1, 7500, 1, '2026-01-02')"
        )
        conn.exec_driver_sql(
            "INSERT INTO alert_rules (watch_id, kind, params, state, enabled)"
            " VALUES (1, 'BACK_IN_STOCK', '{}', '{}', 1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO notifications (watch_id, payload, sent_at, delivery)"
            " VALUES (1, '{}', '2026-01-02', '{}')"
        )
        conn.exec_driver_sql(
            "INSERT INTO channels (id, user_id, kind, config, enabled, created_at)"
            " VALUES (1, 1, 'discord', '{}', 1, '2026-01-01')"
        )
        conn.exec_driver_sql(
            "INSERT INTO watch_channels (watch_id, channel_id, enabled) VALUES (1, 1, 0)"
        )
    command.upgrade(cfg, "head")
    with dbmod.engine.connect() as conn:
        q = conn.exec_driver_sql
        for table in ("users", "watches", "alert_rules", "notifications", "watch_channels"):
            assert q(f"SELECT count(*) FROM {table}").scalar() == 1, table
        # 0008: cada Watch quedó con su producto como único item y su última lectura.
        assert q("SELECT watch_id, product_id, user_id FROM watch_items").all() == [(1, 1, 1)]
        assert q("SELECT last_price, last_best_product_id FROM watches").one() == (7500, 1)
        assert q("PRAGMA foreign_key_check").all() == []
        # Las migraciones apagan las FK; la conexión vuelve al pool con las FK activas.
        assert q("PRAGMA foreign_keys").scalar() == 1


def test_catalogos_de_meli_pasan_al_modo_por_defecto_sin_perder_historial(tmp_path):
    dbmod.configure(f"sqlite:///{tmp_path}/meli.db")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0005")
    with dbmod.engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (id, username, role, active, watch_quota, preferences, created_at)"
            " VALUES (1, 'ana', 'user', 1, 50, '{}', '2026-01-01')"
        )
        for pid, ext in ((1, "MLC49200061"), (2, "MLCU3227804779")):
            conn.exec_driver_sql(
                "INSERT INTO products (id, processor, external_id, variant_id, canonical_url,"
                " title, currency, status, fail_count, next_check_at, created_at)"
                f" VALUES ({pid}, 'mercadolibre', '{ext}', '', 'https://www.mercadolibre.cl/p/{ext}',"
                " 'Switch 2', 'CLP', 'ok', 0, '2026-12-01', '2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO price_points (product_id, price, available, checked_at)"
                f" VALUES ({pid}, 526077, 1, '2026-09-29')"
            )
            conn.exec_driver_sql(
                "INSERT INTO watches (id, user_id, product_id, active, price_at_start, created_at)"
                f" VALUES ({pid}, 1, {pid}, 1, 526077, '2026-01-01')"
            )
        conn.exec_driver_sql(
            "INSERT INTO alert_rules (watch_id, kind, params, state, enabled) VALUES"
            " (1, 'PRICE_CHANGE', '{}', '{\"last_price\": 526077}', 1),"
            " (1, 'BACK_IN_STOCK', '{}', '{\"last_available\": true}', 1)"
        )
    command.upgrade(cfg, "head")
    with dbmod.engine.connect() as conn:
        q = conn.exec_driver_sql
        # El historial del "más barato de todos" quedó en un producto aparte, sin seguidores.
        todos = q("SELECT id, canonical_url FROM products WHERE variant_id = 'todos'").all()
        assert todos == [(3, "https://www.mercadolibre.cl/p/MLC49200061?modo=todos")]
        assert q("SELECT product_id FROM price_points ORDER BY product_id").scalars().all() == [
            2,
            3,
        ]
        # El original parte de cero: sin precio de inicio y con PRICE_CHANGE reiniciada.
        assert q("SELECT price_at_start FROM watches WHERE id = 1").scalar() is None
        states = dict(q("SELECT kind, state FROM alert_rules WHERE watch_id = 1").all())
        assert json.loads(states["PRICE_CHANGE"]) == {"last_price": None}
        assert json.loads(states["BACK_IN_STOCK"]) == {"last_available": True}
        # Las publicaciones /up/ no cambian.
        assert q("SELECT price_at_start FROM watches WHERE id = 2").scalar() == 526077
