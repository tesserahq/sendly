"""Add broadcast sending tables and email tags/metadata/batch_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("emails", sa.Column("batch_id", sa.String(), nullable=True))
    op.add_column("emails", sa.Column("tags", postgresql.JSONB(), nullable=True))
    op.add_column("emails", sa.Column("metadata", postgresql.JSONB(), nullable=True))
    op.create_index("ix_emails_batch_id", "emails", ["batch_id"])

    op.create_table(
        "email_suppressions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("unsubscribed_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_email_suppressions_deleted_at", "email_suppressions", ["deleted_at"]
    )
    op.create_index(
        "uq_email_suppressions_project_email_active",
        "email_suppressions",
        ["project_id", "email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "broadcast_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("request_fingerprint", sa.String(), nullable=True),
        sa.Column("content_spec", postgresql.JSONB(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suppressed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_broadcast_batches_deleted_at", "broadcast_batches", ["deleted_at"]
    )
    op.create_index(
        "uq_broadcast_batches_batch_id_active",
        "broadcast_batches",
        ["batch_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_broadcast_batches_project_idempotency_active",
        "broadcast_batches",
        ["project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "broadcast_recipients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("broadcast_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("prepared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["broadcast_batch_id"], ["broadcast_batches.id"]),
    )
    op.create_index(
        "ix_broadcast_recipients_broadcast_batch_id",
        "broadcast_recipients",
        ["broadcast_batch_id"],
    )
    op.create_index(
        "ix_broadcast_recipients_prepared_suppressed",
        "broadcast_recipients",
        ["broadcast_batch_id", "prepared", "suppressed"],
    )

    op.create_table(
        "email_delivery_payloads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_email", sa.String(), nullable=False),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "attachments", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "custom_headers", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("message_stream", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.UniqueConstraint("email_id", name="uq_email_delivery_payloads_email_id"),
    )

    op.create_table(
        "email_send_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.UniqueConstraint("email_id", name="uq_email_send_outbox_email_id"),
    )
    op.create_index(
        "ix_email_send_outbox_processed_at", "email_send_outbox", ["processed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_send_outbox_processed_at", table_name="email_send_outbox")
    op.drop_table("email_send_outbox")
    op.drop_table("email_delivery_payloads")
    op.drop_index(
        "ix_broadcast_recipients_prepared_suppressed", table_name="broadcast_recipients"
    )
    op.drop_index(
        "ix_broadcast_recipients_broadcast_batch_id", table_name="broadcast_recipients"
    )
    op.drop_table("broadcast_recipients")
    op.drop_index(
        "uq_broadcast_batches_project_idempotency_active",
        table_name="broadcast_batches",
    )
    op.drop_index(
        "uq_broadcast_batches_batch_id_active", table_name="broadcast_batches"
    )
    op.drop_index("ix_broadcast_batches_deleted_at", table_name="broadcast_batches")
    op.drop_table("broadcast_batches")
    op.drop_index(
        "uq_email_suppressions_project_email_active", table_name="email_suppressions"
    )
    op.drop_index("ix_email_suppressions_deleted_at", table_name="email_suppressions")
    op.drop_table("email_suppressions")
    op.drop_index("ix_emails_batch_id", table_name="emails")
    op.drop_column("emails", "metadata")
    op.drop_column("emails", "tags")
    op.drop_column("emails", "batch_id")
