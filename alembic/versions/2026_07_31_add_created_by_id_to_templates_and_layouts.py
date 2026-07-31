"""Add created_by_id to templates and layouts

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-31

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "layouts",
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_layouts_created_by_id_users",
        "layouts",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "templates",
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_templates_created_by_id_users",
        "templates",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_templates_created_by_id_users", "templates", type_="foreignkey"
    )
    op.drop_column("templates", "created_by_id")

    op.drop_constraint("fk_layouts_created_by_id_users", "layouts", type_="foreignkey")
    op.drop_column("layouts", "created_by_id")
