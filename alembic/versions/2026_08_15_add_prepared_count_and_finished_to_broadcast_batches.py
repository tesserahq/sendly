"""Add prepared_count and finished to broadcast_batches

Revision ID: c60466fcd388
Revises: 173abbb1c24e
Create Date: 2026-08-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c60466fcd388"
down_revision: Union[str, None] = "173abbb1c24e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcast_batches",
        sa.Column("prepared_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broadcast_batches",
        sa.Column("finished", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("broadcast_batches", "finished")
    op.drop_column("broadcast_batches", "prepared_count")
