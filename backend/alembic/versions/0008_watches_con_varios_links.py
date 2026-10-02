"""un Watch puede tener varios links (watch_items) y un nombre propio

`watches` se recrea sin `product_id` (SQLite no puede borrar una columna con índice y
FK). La recreación borraría en cascada reglas, avisos y canales si las FK estuvieran
activas: `alembic/env.py` las apaga antes de abrir la transacción y esta migración
se niega a correr si siguen activas. Se recrea con el mismo nombre, así las tablas
hijas siguen apuntando a `watches` sin tocarlas.

Cada Watch existente queda con un item (su producto) y con la última lectura de ese
producto como lectura del grupo.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _foreign_keys_off() -> None:
    if op.get_bind().exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("foreign_keys sigue activo: recrear watches borraría sus hijos")


def upgrade() -> None:
    _foreign_keys_off()
    # Si un intento anterior falló a medias (el DDL en SQLite no va en la transacción).
    op.execute("DROP TABLE IF EXISTS watches_new")
    op.execute(
        """
        CREATE TABLE watches_new (
            id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name VARCHAR(200),
            active BOOLEAN NOT NULL,
            price_at_start INTEGER,
            last_price INTEGER,
            last_available BOOLEAN,
            last_best_product_id INTEGER,
            counted_product_ids JSON,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        INSERT INTO watches_new (id, user_id, name, active, price_at_start, last_price,
                                 last_available, last_best_product_id, counted_product_ids,
                                 created_at)
        SELECT w.id, w.user_id, NULL, w.active, w.price_at_start,
               (SELECT p.price FROM price_points p WHERE p.product_id = w.product_id
                ORDER BY p.checked_at DESC, p.id DESC LIMIT 1),
               (SELECT p.available FROM price_points p WHERE p.product_id = w.product_id
                ORDER BY p.checked_at DESC, p.id DESC LIMIT 1),
               w.product_id, json_array(w.product_id), w.created_at
        FROM watches w
        """
    )
    op.execute(
        """
        CREATE TABLE watch_items (
            id INTEGER NOT NULL,
            watch_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, product_id),
            FOREIGN KEY(watch_id) REFERENCES watches (id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    # Si un usuario seguía el mismo producto dos veces (no debería), queda el más antiguo.
    op.execute(
        """
        INSERT OR IGNORE INTO watch_items (watch_id, product_id, user_id, added_at)
        SELECT id, product_id, user_id, created_at FROM watches ORDER BY id
        """
    )
    op.execute("DROP TABLE watches")
    op.execute("ALTER TABLE watches_new RENAME TO watches")
    op.execute("CREATE INDEX ix_watches_user_id ON watches (user_id)")
    op.execute("CREATE INDEX ix_watch_items_watch_id ON watch_items (watch_id)")
    op.execute("CREATE INDEX ix_watch_items_product_id ON watch_items (product_id)")
    # Un Watch sin item (el duplicado ignorado arriba) no sirve: se borra con sus hijos.
    orphan = "SELECT id FROM watches WHERE id NOT IN (SELECT watch_id FROM watch_items)"
    for child in ("alert_rules", "notifications", "watch_channels"):
        op.execute(f"DELETE FROM {child} WHERE watch_id IN ({orphan})")
    op.execute(f"DELETE FROM watches WHERE id IN ({orphan})")
    bad = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise RuntimeError(f"FK rotas tras recrear watches: {bad[:5]}")


def downgrade() -> None:
    raise NotImplementedError("sin vuelta atrás: restaurar desde un backup")
