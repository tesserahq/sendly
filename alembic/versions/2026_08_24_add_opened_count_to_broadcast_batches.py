"""Add opened_count to broadcast_batches

Revision ID: 3f9d2c7a5e1b
Revises: 8b1e6a2d9f3c
Create Date: 2026-08-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3f9d2c7a5e1b"
down_revision: Union[str, None] = "8b1e6a2d9f3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcast_batches",
        sa.Column("opened_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("broadcast_batches", "opened_count")
