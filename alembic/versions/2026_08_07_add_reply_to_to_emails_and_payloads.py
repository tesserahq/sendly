"""Add reply_to to emails and email_delivery_payloads

Revision ID: 173abbb1c24e
Revises: f4c71759e9d9
Create Date: 2026-08-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "173abbb1c24e"
down_revision: Union[str, None] = "f4c71759e9d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("emails", sa.Column("reply_to", sa.String(), nullable=True))
    op.add_column(
        "email_delivery_payloads", sa.Column("reply_to", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("email_delivery_payloads", "reply_to")
    op.drop_column("emails", "reply_to")
