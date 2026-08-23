"""Add delivered_count, bounced_count, complained_count to broadcast_batches

Revision ID: 8b1e6a2d9f3c
Revises: c60466fcd388
Create Date: 2026-08-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8b1e6a2d9f3c"
down_revision: Union[str, None] = "c60466fcd388"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcast_batches",
        sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broadcast_batches",
        sa.Column("bounced_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broadcast_batches",
        sa.Column("complained_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("broadcast_batches", "complained_count")
    op.drop_column("broadcast_batches", "bounced_count")
    op.drop_column("broadcast_batches", "delivered_count")
