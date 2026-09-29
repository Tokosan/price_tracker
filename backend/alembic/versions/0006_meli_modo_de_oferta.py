"""MercadoLibre: los catálogos existentes pasan al modo por defecto (tienda oficial)

Hasta ahora un link /p/MLC… seguía el más barato de todos, que suele ser una compra
internacional. Ese historial se mueve a un producto nuevo en modo `todos` (sin
seguidores, no se revisa) y el producto original, ahora en modo por defecto, parte de
cero: sin precio de inicio y con las referencias de las reglas de precio reiniciadas,
para que el salto de precio no dispare avisos. Solo UPDATE/INSERT: no recrea tablas.

Revision ID: 0006
Revises: 0005
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Estado inicial de cada regla de precio sin lectura previa (ver rules.initial_state).
RESET = {
    "TARGET_PRICE": {"armed": True},
    "DISCOUNT_PCT": {"armed": True},
    "PRICE_DROP": {"last_notified_price": None},
    "PRICE_UP": {"last_notified_price": None},
    "PRICE_CHANGE": {"last_price": None},
}
COPY = (
    "processor, external_id, canonical_url, title, image_url, currency, status, fail_count,"
    " last_error, next_check_at, last_checked_at, last_manual_check_at, created_at"
)


def upgrade() -> None:
    conn = op.get_bind()
    # Mismo formato que guarda SQLAlchemy en SQLite para un DateTime.
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    catalogs = conn.execute(
        sa.text(
            "SELECT id, canonical_url FROM products WHERE processor = 'mercadolibre'"
            " AND external_id LIKE 'MLC%' AND external_id NOT LIKE 'MLCU%' AND variant_id = ''"
        )
    ).all()
    for pid, url in catalogs:
        conn.execute(
            sa.text(
                f"INSERT INTO products ({COPY}, variant_id) SELECT {COPY}, 'todos'"
                " FROM products WHERE id = :pid"
            ),
            {"pid": pid},
        )
        new_id = conn.execute(sa.text("SELECT last_insert_rowid()")).scalar()
        conn.execute(
            sa.text("UPDATE products SET canonical_url = :url WHERE id = :id"),
            {"url": url.split("?")[0] + "?modo=todos", "id": new_id},
        )
        for table in ("price_points", "anomalies"):
            conn.execute(
                sa.text(f"UPDATE {table} SET product_id = :new WHERE product_id = :old"),
                {"new": new_id, "old": pid},
            )
        conn.execute(
            sa.text("UPDATE watches SET price_at_start = NULL WHERE product_id = :pid"),
            {"pid": pid},
        )
        for kind, state in RESET.items():
            conn.execute(
                sa.text(
                    "UPDATE alert_rules SET state = :state WHERE kind = :kind"
                    " AND watch_id IN (SELECT id FROM watches WHERE product_id = :pid)"
                ),
                {"state": json.dumps(state), "kind": kind, "pid": pid},
            )
        conn.execute(
            sa.text(
                "UPDATE products SET next_check_at = :now, fail_count = 0, status = 'ok',"
                " last_error = NULL WHERE id = :pid"
            ),
            {"now": now, "pid": pid},
        )


def downgrade() -> None:
    # Irreversible sin perder datos nuevos: el historial movido queda en el producto `todos`.
    pass
