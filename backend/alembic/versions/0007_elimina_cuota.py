"""elimina la cuota de productos por usuario

`users` tiene hijos: nada de batch (la recreación borraría en cascada). La columna
no tiene índice ni FK, así que basta un DROP COLUMN nativo (SQLite >= 3.35).

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN watch_quota")


def downgrade() -> None:
    op.add_column(
        "users", sa.Column("watch_quota", sa.Integer(), nullable=False, server_default="50")
    )
