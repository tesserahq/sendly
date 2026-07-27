"""Integration tests for SendBroadcastCommand: atomic batch/recipient write,
server-generated batch_id, suppressed/queued counts from one bulk lookup, and
idempotency. The prepare-stage dispatch is patched out here — it's covered by
its own publisher tests — so these tests stay focused on the accept stage.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.commands.send_broadcast_command import SendBroadcastCommand
from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient
from app.models.email import Email
from app.models.email_suppression import EmailSuppression
from app.schemas.broadcast import BroadcastCreateRequest


@pytest.fixture(autouse=True)
def no_prepare_dispatch():
    """Prevent the accept stage from actually dispatching Celery tasks —
    those need a DB session that can see this test's uncommitted rows, which
    the nested-transaction `db` fixture can't provide (see conftest.py)."""
    with patch(
        "app.commands.send_broadcast_command.BroadcastPreparePublisher"
    ) as MockPublisher:
        yield MockPublisher


def _make_request(project_id, **overrides):
    defaults = dict(
        project_id=project_id,
        from_email="sender@example.com",
        subject="Hello",
        html="<p>Hi ${first_name}</p>",
        recipients=[
            {"email": "a@example.com", "first_name": "Alice"},
            {"email": "b@example.com", "first_name": "Bob"},
        ],
    )
    defaults.update(overrides)
    return BroadcastCreateRequest(**defaults)


class TestContentValidation:
    """Content-level mistakes affect every recipient identically, so they're
    rejected up front instead of silently failing each recipient, one by
    one, deep in the async prepare stage."""

    def test_missing_subject_with_inline_html_is_rejected(self, db):
        req = _make_request(uuid4(), subject=None)
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 422
        assert "subject" in exc_info.value.detail.lower()
        assert db.query(BroadcastBatch).count() == 0

    def test_missing_from_email_with_inline_html_is_rejected(self, db):
        req = _make_request(uuid4(), from_email=None)
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 422
        assert "from_email" in exc_info.value.detail.lower()

    def test_missing_html_and_template_is_rejected(self, db):
        req = _make_request(uuid4(), html=None)
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 422

    def test_both_template_and_inline_html_is_rejected(self, db):
        req = _make_request(uuid4(), template_alias="welcome")
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 400

    def test_unresolvable_template_is_rejected(self, db):
        req = _make_request(uuid4(), html=None, template_alias="nonexistent")
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 404

    def test_valid_template_with_missing_from_email_is_rejected(self, db, faker):
        from app.models.template import Template

        template = Template(
            alias=faker.slug(),
            subject="Hi ${first_name}",
            html="<p>Hi ${first_name}</p>",
        )
        db.add(template)
        db.commit()

        req = _make_request(
            uuid4(), html=None, from_email=None, template_alias=template.alias
        )
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(req)
        assert exc_info.value.status_code == 422


class TestSendBroadcastCommand:
    def test_creates_batch_and_recipient_rows(self, db):
        project_id = uuid4()
        req = _make_request(project_id)

        batch = SendBroadcastCommand(db).execute(req)

        assert batch.project_id == project_id
        assert batch.queued_count == 2
        assert batch.suppressed_count == 0

        recipients = (
            db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.broadcast_batch_id == batch.id)
            .all()
        )
        assert len(recipients) == 2
        assert {r.email for r in recipients} == {"a@example.com", "b@example.com"}

    def test_generates_server_side_batch_id(self, db):
        req = _make_request(uuid4())
        batch = SendBroadcastCommand(db).execute(req)
        assert batch.batch_id
        assert len(batch.batch_id) > 0

    def test_does_not_create_email_rows(self, db):
        req = _make_request(uuid4())
        SendBroadcastCommand(db).execute(req)
        assert (
            db.query(Email)
            .filter(Email.to_email.in_(["a@example.com", "b@example.com"]))
            .count()
            == 0
        )

    def test_does_not_call_rendering_service(self, db):
        req = _make_request(uuid4())
        with patch(
            "app.services.email_rendering_service.EmailRenderingService.resolve"
        ) as mock_resolve:
            SendBroadcastCommand(db).execute(req)
        mock_resolve.assert_not_called()

    def test_excludes_suppressed_recipients_from_queued_count(self, db):
        project_id = uuid4()
        db.add(
            EmailSuppression(
                project_id=project_id,
                email="b@example.com",
                unsubscribed_at="2026-01-01T00:00:00+00:00",
                source="test",
            )
        )
        db.commit()

        req = _make_request(project_id)
        batch = SendBroadcastCommand(db).execute(req)

        assert batch.queued_count == 1
        assert batch.suppressed_count == 1

        recipients = {
            r.email: r.suppressed
            for r in db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.broadcast_batch_id == batch.id)
            .all()
        }
        assert recipients["a@example.com"] is False
        assert recipients["b@example.com"] is True

    def test_idempotency_key_returns_original_result(self, db):
        project_id = uuid4()
        req = _make_request(project_id, idempotency_key="my-key")

        first = SendBroadcastCommand(db).execute(req)
        second = SendBroadcastCommand(db).execute(req)

        assert first.id == second.id
        assert first.batch_id == second.batch_id
        # No duplicate recipient rows were created on the retry.
        assert (
            db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.broadcast_batch_id == first.id)
            .count()
            == 2
        )

    def test_query_count_does_not_scale_with_recipient_count(self, db):
        """Regression test for the problem the prepare/send split exists to
        fix: acceptance is O(1) bulk-suppression-lookup + O(1) bulk-insert
        round-trips, not one query/insert per recipient.

        Counts actual SQL statements issued rather than wall-clock time —
        deterministic, unlike timing, which is noisy under test-suite load.
        """
        from sqlalchemy import event

        def _query_count(recipient_count):
            recipients = [
                {"email": f"user{i}@example.com"} for i in range(recipient_count)
            ]
            req = _make_request(uuid4(), recipients=recipients)

            count = 0

            def _count_statement(*args, **kwargs):
                nonlocal count
                count += 1

            event.listen(db.bind, "before_cursor_execute", _count_statement)
            try:
                SendBroadcastCommand(db).execute(req)
            finally:
                event.remove(db.bind, "before_cursor_execute", _count_statement)
            return count

        small_count = _query_count(10)
        large_count = _query_count(5000)

        # A per-recipient-loop implementation would issue ~500x more queries
        # for 5000 vs 10 recipients (one query/insert per recipient). A
        # bulk-insert implementation issues a small, fixed number of
        # statements regardless of recipient count — SQLAlchemy's
        # insertmanyvalues may still split a very large bulk insert into a
        # handful of batched statements, so allow a small constant-factor
        # difference rather than requiring exact equality.
        assert large_count <= small_count + 10
        assert large_count < 5000 / 10  # nowhere near one-statement-per-recipient

    def test_idempotency_key_with_different_content_conflicts(self, db):
        project_id = uuid4()
        req = _make_request(project_id, idempotency_key="my-key")
        SendBroadcastCommand(db).execute(req)

        different_req = _make_request(
            project_id, idempotency_key="my-key", subject="Different subject"
        )
        with pytest.raises(HTTPException) as exc_info:
            SendBroadcastCommand(db).execute(different_req)

        assert exc_info.value.status_code == 409


class TestGlobalBroadcast:
    """project_id is optional to support org-wide (not project-scoped)
    broadcasts. These pass project_id=None through _make_request and check
    that suppression/idempotency logic — normally project_id-scoped — has
    an explicit branch for the global case instead of silently no-op'ing."""

    def test_creates_batch_with_null_project_id(self, db):
        req = _make_request(None)
        batch = SendBroadcastCommand(db).execute(req)
        assert batch.project_id is None
        assert batch.queued_count == 2

    def test_excludes_recipient_suppressed_in_any_project(self, db):
        other_project = uuid4()
        db.add(
            EmailSuppression(
                project_id=other_project,
                email="b@example.com",
                unsubscribed_at="2026-01-01T00:00:00+00:00",
                source="test",
            )
        )
        db.commit()

        req = _make_request(None)
        batch = SendBroadcastCommand(db).execute(req)

        assert batch.queued_count == 1
        assert batch.suppressed_count == 1

    def test_idempotency_key_returns_original_result_for_global_batch(self, db):
        req = _make_request(None, idempotency_key="global-key")

        first = SendBroadcastCommand(db).execute(req)
        second = SendBroadcastCommand(db).execute(req)

        assert first.id == second.id
        assert (
            db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.broadcast_batch_id == first.id)
            .count()
            == 2
        )

    def test_global_idempotency_key_is_independent_from_project_scoped_key(self, db):
        """A global batch (project_id=None) and a project-scoped batch must
        not collide on the same idempotency_key — regression test for the
        NULL-never-equals-NULL SQL pitfall in
        BroadcastRepository.get_batch_by_idempotency_key."""
        project_id = uuid4()
        project_req = _make_request(project_id, idempotency_key="shared-key")
        global_req = _make_request(None, idempotency_key="shared-key")

        project_batch = SendBroadcastCommand(db).execute(project_req)
        global_batch = SendBroadcastCommand(db).execute(global_req)

        assert project_batch.id != global_batch.id
