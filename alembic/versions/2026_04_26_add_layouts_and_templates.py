"""Add layouts and templates tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "layouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_layouts_alias", "layouts", ["alias"])
    op.create_index("ix_layouts_deleted_at", "layouts", ["deleted_at"])
    op.create_index(
        "uq_layouts_alias_active",
        "layouts",
        ["alias"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("from_email", sa.String(), nullable=True),
        sa.Column("reply_to", sa.String(), nullable=True),
        sa.Column("layout_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["layout_id"], ["layouts.id"]),
    )
    op.create_index("ix_templates_alias", "templates", ["alias"])
    op.create_index("ix_templates_deleted_at", "templates", ["deleted_at"])
    op.create_index(
        "uq_templates_alias_active",
        "templates",
        ["alias"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_templates_alias_active", table_name="templates")
    op.drop_index("ix_templates_deleted_at", table_name="templates")
    op.drop_index("ix_templates_alias", table_name="templates")
    op.drop_table("templates")
    op.drop_index("uq_layouts_alias_active", table_name="layouts")
    op.drop_index("ix_layouts_deleted_at", table_name="layouts")
    op.drop_index("ix_layouts_alias", table_name="layouts")
    op.drop_table("layouts")
