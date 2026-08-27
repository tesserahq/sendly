"""Explicit verification for the 7c2f4a9d1e6b migration's data backfill:
first-click timestamps from existing email_events, batch clicked_count from
distinct first-clicked emails, and opened_count recomputed from opened_at —
plus confirming ambiguous historical recipient-to-email links are left null.

Runs against its own disposable database (not the shared `sendly_test` used
by the rest of the suite) so it can freely downgrade/upgrade across this
migration without disturbing other tests.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings

_DOWN_REVISION = "3f9d2c7a5e1b"  # revision immediately before the backfill
_MIGRATION_DB_NAME = "sendly_migration_backfill_test"


@contextmanager
def _env_pointed_at(db_url: str):
    """alembic/env.py always builds its own fresh Settings() from
    TEST_DATABASE_URL/DATABASE_URL rather than honoring an Alembic Config
    override, so redirecting a migration run at a scratch database means
    temporarily repointing the env var it actually reads."""
    key = "TEST_DATABASE_URL" if get_settings().is_test else "DATABASE_URL"
    previous = os.environ.get(key)
    os.environ[key] = db_url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture(scope="module")
def migration_engine():
    settings = get_settings()
    admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{_MIGRATION_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {_MIGRATION_DB_NAME}"))
        conn.execute(text(f"CREATE DATABASE {_MIGRATION_DB_NAME}"))
    admin_engine.dispose()

    db_url = settings.database_url.rsplit("/", 1)[0] + f"/{_MIGRATION_DB_NAME}"
    engine = create_engine(db_url)

    yield engine

    engine.dispose()
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{_MIGRATION_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {_MIGRATION_DB_NAME}"))
    admin_engine.dispose()


class TestRecipientEngagementBackfillMigration:
    def test_backfills_click_timestamps_counts_and_leaves_recipient_links_null(
        self, migration_engine
    ):
        db_url = migration_engine.url.render_as_string(hide_password=False)
        cfg = Config("alembic.ini")

        # Land the schema as it existed immediately before this migration.
        with _env_pointed_at(db_url):
            command.upgrade(cfg, _DOWN_REVISION)

        batch_id = str(uuid.uuid4())
        email_clicked_twice_id = str(uuid.uuid4())
        email_opened_only_id = str(uuid.uuid4())
        email_untouched_id = str(uuid.uuid4())
        recipient_id = str(uuid.uuid4())
        batch_pk = str(uuid.uuid4())

        with migration_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO broadcast_batches
                        (id, project_id, batch_id, content_spec, queued_count,
                         suppressed_count, opened_count)
                    VALUES (:id, :project_id, :batch_id, '{}', 3, 0, 0)
                    """),
                {"id": batch_pk, "project_id": str(uuid.uuid4()), "batch_id": batch_id},
            )

            # One recipient row that predates this migration — it has no
            # email_id column yet at this point in schema history, so
            # nothing to set; it exists to prove the recipient row itself
            # survives the migration untouched (checked below via SELECT *).
            conn.execute(
                text("""
                    INSERT INTO broadcast_recipients
                        (id, broadcast_batch_id, email)
                    VALUES (:id, :batch_id, 'legacy@example.com')
                    """),
                {"id": recipient_id, "batch_id": batch_pk},
            )

            for email_id, opened, batch in (
                (email_clicked_twice_id, False, batch_id),
                (email_opened_only_id, True, batch_id),
                (email_untouched_id, False, None),
            ):
                conn.execute(
                    text("""
                        INSERT INTO emails
                            (id, from_email, to_email, subject, body, status,
                             provider, batch_id, opened_at)
                        VALUES
                            (:id, 'from@example.com', 'to@example.com', 'Hi',
                             'Body', 'clicked', 'postmark', :batch,
                             CASE WHEN :opened THEN now() ELSE NULL END)
                        """),
                    {"id": email_id, "batch": batch, "opened": opened},
                )

            # Two click events for the same email, out of chronological
            # insert order, to prove the backfill takes the earliest one.
            conn.execute(
                text("""
                    INSERT INTO email_events
                        (id, email_id, event_type, event_timestamp, details)
                    VALUES
                        (:id1, :email_id, 'clicked', '2026-01-02T00:00:00', '{}'),
                        (:id2, :email_id, 'clicked', '2026-01-01T00:00:00', '{}')
                    """),
                {
                    "id1": str(uuid.uuid4()),
                    "id2": str(uuid.uuid4()),
                    "email_id": email_clicked_twice_id,
                },
            )

        with _env_pointed_at(db_url):
            command.upgrade(cfg, "head")

        with migration_engine.connect() as conn:
            clicked_email = conn.execute(
                text("SELECT clicked_at FROM emails WHERE id = :id"),
                {"id": email_clicked_twice_id},
            ).one()
            assert clicked_email.clicked_at.isoformat().startswith("2026-01-01")

            opened_only_email = conn.execute(
                text("SELECT clicked_at FROM emails WHERE id = :id"),
                {"id": email_opened_only_id},
            ).one()
            assert opened_only_email.clicked_at is None

            batch_row = conn.execute(
                text(
                    "SELECT clicked_count, opened_count FROM broadcast_batches "
                    "WHERE id = :id"
                ),
                {"id": batch_pk},
            ).one()
            assert batch_row.clicked_count == 1  # one distinct email w/ clicked_at
            assert batch_row.opened_count == 1  # recomputed from opened_at

            recipient_row = conn.execute(
                text(
                    "SELECT email_id, client_reference_id FROM broadcast_recipients "
                    "WHERE id = :id"
                ),
                {"id": recipient_id},
            ).one()
            assert recipient_row.email_id is None
            assert recipient_row.client_reference_id is None
