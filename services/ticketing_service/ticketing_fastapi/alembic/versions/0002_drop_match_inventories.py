"""Drop local match inventory table.

Revision ID: 0002_drop_match_inventories
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_drop_match_inventories"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("match_inventories")


def downgrade() -> None:
    op.create_table(
        "match_inventories",
        sa.Column("match_id", sa.Integer(), primary_key=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("reserved <= capacity", name="reserved_not_exceed_capacity"),
    )
