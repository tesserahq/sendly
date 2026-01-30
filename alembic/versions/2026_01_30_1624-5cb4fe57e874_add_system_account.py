"""add system account

Revision ID: 5cb4fe57e874
Revises: initialize_database
Create Date: 2026-01-30 16:24:10.646419

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5cb4fe57e874"
down_revision: Union[str, None] = "initialize_database"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("service_account", sa.Boolean, default=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "service_account")
