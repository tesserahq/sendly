"""Celery-eager tests for prepare_broadcast_chunk_task.

Uses `real_db`/`broadcast_client`-style direct DB access (not the nested-
transaction `db` fixture) because the task opens its own DB session via
SessionLocal(), exactly as it does in production — see the `real_db` fixture
docstring in conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.constants.email import EmailStatus
from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient
from app.models.email import Email
from app.models.email_delivery_payload import EmailDeliveryPayload
from app.models.email_send_outbox import EmailSendOutbox
from app.models.email_suppression import EmailSuppression
from app.tasks.prepare_broadcast_chunk_task import prepare_broadcast_chunk_task


@pytest.fixture(autouse=True)
def no_outbox_dispatch():
    """This task's own outbox-publisher fast path is out of scope here — it's
    covered by test_broadcast_outbox_publisher.py and the send-chunk task
    tests. Stub it so this file only exercises the prepare stage."""
    with patch(
        "app.tasks.prepare_broadcast_chunk_task.BroadcastOutboxPublisher"
    ) as MockPublisher:
        yield MockPublisher


def _make_batch(real_db, project_id, **content_spec_overrides):
    content_spec = {
        "html": "<p>Hi ${first_name}</p>",
        "text": None,
        "template_id": None,
        "template_alias": None,
        "template_variables": {},
        "subject": "Hello",
        "from_email": "sender@example.com",
        "custom_headers": {},
        "attachments": [],
        "tags": ["campaign-x"],
        "metadata": {"source": "test"},
    }
    content_spec.update(content_spec_overrides)

    batch = BroadcastBatch(
        project_id=project_id,
        batch_id=str(uuid4()),
        idempotency_key=None,
        request_fingerprint="fp",
        content_spec=content_spec,
        queued_count=1,
        suppressed_count=0,
    )
    real_db.add(batch)
    real_db.commit()
    real_db.refresh(batch)
    return batch


def _make_recipient(real_db, batch, **overrides):
    defaults = dict(
        broadcast_batch_id=batch.id,
        email="recipient@example.com",
        first_name="Alice",
        last_name=None,
        attributes={},
        suppressed=False,
        prepared=False,
    )
    defaults.update(overrides)
    recipient = BroadcastRecipient(**defaults)
    real_db.add(recipient)
    real_db.commit()
    real_db.refresh(recipient)
    return recipient


class TestPrepareBroadcastChunkTask:
    def test_creates_email_payload_and_outbox_rows(self, real_db):
        project_id = uuid4()
        batch = _make_batch(real_db, project_id)
        recipient = _make_recipient(real_db, batch)

        with patch(
            "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        email = (
            real_db.query(Email)
            .filter(Email.to_email == "recipient@example.com")
            .first()
        )
        assert email is not None
        assert email.status == EmailStatus.QUEUED
        assert email.batch_id == batch.batch_id
        assert email.tags == ["campaign-x"]
        assert email.metadata_ == {"source": "test"}
        assert "Hi Alice" in email.body

        payload = (
            real_db.query(EmailDeliveryPayload)
            .filter(EmailDeliveryPayload.email_id == email.id)
            .first()
        )
        assert payload is not None
        assert payload.to_email == "recipient@example.com"

        outbox_entry = (
            real_db.query(EmailSendOutbox)
            .filter(EmailSendOutbox.email_id == email.id)
            .first()
        )
        assert outbox_entry is not None

        recipient_row = (
            real_db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id == recipient.id)
            .first()
        )
        assert recipient_row.prepared is True

    def test_merges_recipient_attributes_into_template_variables(self, real_db):
        project_id = uuid4()
        batch = _make_batch(
            real_db,
            project_id,
            html="<p>Hi ${first_name}, your plan is ${plan}</p>",
        )
        recipient = _make_recipient(
            real_db,
            batch,
            first_name="Bob",
            attributes={"plan": "Pro"},
        )

        with patch(
            "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        email = (
            real_db.query(Email)
            .filter(Email.to_email == "recipient@example.com")
            .first()
        )
        assert "Hi Bob, your plan is Pro" in email.body

    def test_skips_recipient_suppressed_since_acceptance(self, real_db):
        project_id = uuid4()
        batch = _make_batch(real_db, project_id)
        recipient = _make_recipient(real_db, batch, suppressed=False)
        real_db.add(
            EmailSuppression(
                project_id=project_id,
                email="recipient@example.com",
                unsubscribed_at="2026-01-01T00:00:00+00:00",
                source="test",
            )
        )
        real_db.commit()

        prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        assert (
            real_db.query(Email)
            .filter(Email.to_email == "recipient@example.com")
            .first()
            is None
        )
        recipient_row = (
            real_db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id == recipient.id)
            .first()
        )
        assert recipient_row.prepared is True

    def test_rendering_failure_for_one_recipient_does_not_block_others(self, real_db):
        # Both recipients share a template requiring "plan"; only the second
        # recipient supplies it via per-recipient attributes, so the first
        # fails to render while the second succeeds in the same chunk.
        project_id = uuid4()
        batch = _make_batch(real_db, project_id, html="<p>Plan: ${plan}</p>")
        broken_recipient = _make_recipient(
            real_db, batch, email="broken@example.com", attributes={}
        )
        ok_recipient = _make_recipient(
            real_db,
            batch,
            email="ok@example.com",
            attributes={"plan": "Pro"},
        )

        with (
            patch(
                "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
            ) as mock_provider,
            patch("app.tasks.prepare_broadcast_chunk_task.logger") as mock_logger,
        ):
            mock_provider.return_value.provider_id = "postmark"
            prepare_broadcast_chunk_task(
                str(batch.id), [str(broken_recipient.id), str(ok_recipient.id)]
            )

        warning_args = mock_logger.warning.call_args_list[0].args
        assert "Missing variable(s): ['plan']" in str(warning_args[-1])

        real_db.expire_all()
        assert (
            real_db.query(Email).filter(Email.to_email == "broken@example.com").first()
            is None
        )
        ok_email = (
            real_db.query(Email).filter(Email.to_email == "ok@example.com").first()
        )
        assert ok_email is not None
        assert "Plan: Pro" in ok_email.body

        for rid in (broken_recipient.id, ok_recipient.id):
            row = (
                real_db.query(BroadcastRecipient)
                .filter(BroadcastRecipient.id == rid)
                .first()
            )
            assert row.prepared is True


class TestRecipientToEmailLink:
    """The nullable, unique broadcast_recipients.email_id relationship is
    populated by the prepare stage for successfully rendered recipients
    only — suppressed recipients and rendering failures never get one."""

    def test_successfully_prepared_recipient_is_linked_to_its_email(self, real_db):
        project_id = uuid4()
        batch = _make_batch(real_db, project_id)
        recipient = _make_recipient(real_db, batch)

        with patch(
            "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        email = (
            real_db.query(Email)
            .filter(Email.to_email == "recipient@example.com")
            .first()
        )
        recipient_row = (
            real_db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id == recipient.id)
            .first()
        )
        assert recipient_row.email_id == email.id

    def test_suppressed_recipient_has_no_email_link(self, real_db):
        project_id = uuid4()
        batch = _make_batch(real_db, project_id)
        recipient = _make_recipient(real_db, batch, suppressed=False)
        real_db.add(
            EmailSuppression(
                project_id=project_id,
                email="recipient@example.com",
                unsubscribed_at="2026-01-01T00:00:00+00:00",
                source="test",
            )
        )
        real_db.commit()

        prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        recipient_row = (
            real_db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id == recipient.id)
            .first()
        )
        assert recipient_row.email_id is None

    def test_rendering_failure_leaves_recipient_unlinked(self, real_db):
        project_id = uuid4()
        batch = _make_batch(real_db, project_id, html="<p>Plan: ${plan}</p>")
        recipient = _make_recipient(real_db, batch, attributes={})

        with (
            patch(
                "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
            ) as mock_provider,
            patch("app.tasks.prepare_broadcast_chunk_task.logger"),
        ):
            mock_provider.return_value.provider_id = "postmark"
            prepare_broadcast_chunk_task(str(batch.id), [str(recipient.id)])

        real_db.expire_all()
        recipient_row = (
            real_db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id == recipient.id)
            .first()
        )
        assert recipient_row.email_id is None
