"""categorías por usuario para organizar los watches

Solo tablas nuevas (`create_table`): no se recrea ninguna tabla con hijos.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])
    op.create_table(
        "watch_categories",
        sa.Column("watch_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["watch_id"], ["watches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("watch_id", "category_id"),
    )
    op.create_index("ix_watch_categories_category_id", "watch_categories", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_watch_categories_category_id", table_name="watch_categories")
    op.drop_table("watch_categories")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")
