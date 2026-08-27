"""Add caller reference, recipient-to-email link, click tracking, and
clicked_count for broadcast recipient engagement results.

Revision ID: 7c2f4a9d1e6b
Revises: 3f9d2c7a5e1b
Create Date: 2026-08-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "7c2f4a9d1e6b"
down_revision: Union[str, None] = "3f9d2c7a5e1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcast_recipients",
        sa.Column("client_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "broadcast_recipients",
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_broadcast_recipients_email_id",
        "broadcast_recipients",
        "emails",
        ["email_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_broadcast_recipients_email_id", "broadcast_recipients", ["email_id"]
    )
    # Postgres treats NULL as distinct in unique constraints, so recipients
    # without a caller reference are unaffected by this constraint.
    op.create_unique_constraint(
        "uq_broadcast_recipients_batch_reference",
        "broadcast_recipients",
        ["broadcast_batch_id", "client_reference_id"],
    )
    op.create_index(
        "ix_broadcast_recipients_batch_created",
        "broadcast_recipients",
        ["broadcast_batch_id", "created_at", "id"],
    )

    op.add_column("emails", sa.Column("clicked_at", sa.DateTime(), nullable=True))

    op.add_column(
        "broadcast_batches",
        sa.Column("clicked_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Backfill first-click timestamps from the earliest stored click event
    # per existing email. Excludes soft-deleted emails/events (deleted_at IS
    # NOT NULL) — the app's soft-delete filter hides them from every ORM
    # query, so a raw-SQL backfill must exclude them too, or counts here
    # would disagree with what the app ever computes at runtime.
    op.execute("""
        UPDATE emails e
        SET clicked_at = sub.first_clicked
        FROM (
            SELECT ee.email_id, MIN(ee.event_timestamp) AS first_clicked
            FROM email_events ee
            WHERE ee.event_type = 'clicked' AND ee.deleted_at IS NULL
            GROUP BY ee.email_id
        ) sub
        WHERE e.id = sub.email_id AND e.clicked_at IS NULL AND e.deleted_at IS NULL
        """)

    # Backfill batch clicked_count from distinct emails with a click
    # timestamp.
    op.execute("""
        UPDATE broadcast_batches b
        SET clicked_count = sub.cnt
        FROM (
            SELECT batch_id, COUNT(*) AS cnt
            FROM emails
            WHERE clicked_at IS NOT NULL AND batch_id IS NOT NULL
                AND deleted_at IS NULL
            GROUP BY batch_id
        ) sub
        WHERE b.batch_id = sub.batch_id AND b.deleted_at IS NULL
        """)

    # Recompute opened_count from first-open timestamps so both engagement
    # counters start from the same first-occurrence semantics. Reset first so
    # batches with no first-open emails end up at zero rather than keeping a
    # stale value.
    op.execute("UPDATE broadcast_batches SET opened_count = 0 WHERE deleted_at IS NULL")
    op.execute("""
        UPDATE broadcast_batches b
        SET opened_count = sub.cnt
        FROM (
            SELECT batch_id, COUNT(*) AS cnt
            FROM emails
            WHERE opened_at IS NOT NULL AND batch_id IS NOT NULL
                AND deleted_at IS NULL
            GROUP BY batch_id
        ) sub
        WHERE b.batch_id = sub.batch_id AND b.deleted_at IS NULL
        """)

    # Not backfilled: broadcast_recipients.email_id for historical batches.
    # Duplicate addresses are valid, so correlating by email would create
    # false links; historical rows stay visible with null email/engagement
    # fields instead.


def downgrade() -> None:
    op.drop_column("broadcast_batches", "clicked_count")
    op.drop_column("emails", "clicked_at")
    op.drop_index(
        "ix_broadcast_recipients_batch_created", table_name="broadcast_recipients"
    )
    op.drop_constraint(
        "uq_broadcast_recipients_batch_reference",
        "broadcast_recipients",
        type_="unique",
    )
    op.drop_constraint(
        "uq_broadcast_recipients_email_id", "broadcast_recipients", type_="unique"
    )
    op.drop_constraint(
        "fk_broadcast_recipients_email_id", "broadcast_recipients", type_="foreignkey"
    )
    op.drop_column("broadcast_recipients", "email_id")
    op.drop_column("broadcast_recipients", "client_reference_id")
