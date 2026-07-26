"""Celery-eager tests for send_broadcast_chunk_task. Uses `real_db` since the
task opens its own DB session — see conftest.py's `real_db` fixture docstring.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from app.constants.email import EmailStatus
from app.models.email import Email
from app.models.email_delivery_payload import EmailDeliveryPayload
from app.models.email_send_outbox import EmailSendOutbox
from app.models.email_suppression import EmailSuppression
from app.providers.base import EmailSendResult
from app.tasks.send_broadcast_chunk_task import send_broadcast_chunk_task


def _make_email_with_payload(real_db, project_id, to_email, **email_overrides):
    email_defaults = dict(
        project_id=project_id,
        from_email="sender@example.com",
        to_email=to_email,
        subject="Hello",
        body="<p>Hi</p>",
        status=EmailStatus.QUEUED,
        provider="postmark",
    )
    email_defaults.update(email_overrides)
    email = Email(**email_defaults)
    real_db.add(email)
    real_db.commit()
    real_db.refresh(email)

    payload = EmailDeliveryPayload(
        email_id=email.id,
        from_email=email.from_email,
        to_email=to_email,
        subject=email.subject,
        html=email.body,
        text=None,
        attachments=[],
        custom_headers={},
        message_stream=None,
    )
    real_db.add(payload)

    outbox = EmailSendOutbox(email_id=email.id)
    real_db.add(outbox)
    real_db.commit()

    return email


class TestSendBroadcastChunkTask:
    def test_sends_batch_and_records_success(self, real_db):
        project_id = uuid4()
        email = _make_email_with_payload(real_db, project_id, "user@example.com")

        with patch(
            "app.tasks.send_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.send_batch.return_value = [
                EmailSendResult(ok=True, provider_message_id="pm-1")
            ]
            send_broadcast_chunk_task([str(email.id)])

        real_db.expire_all()
        updated = real_db.query(Email).filter(Email.id == email.id).first()
        assert updated.status == EmailStatus.SENT
        assert updated.provider_message_id == "pm-1"

        outbox = (
            real_db.query(EmailSendOutbox)
            .filter(EmailSendOutbox.email_id == email.id)
            .first()
        )
        assert outbox.processed_at is not None

    def test_records_suppressed_instead_of_attempting_send(self, real_db):
        project_id = uuid4()
        email = _make_email_with_payload(real_db, project_id, "unsub@example.com")
        real_db.add(
            EmailSuppression(
                project_id=project_id,
                email="unsub@example.com",
                unsubscribed_at="2026-01-01T00:00:00+00:00",
                source="test",
            )
        )
        real_db.commit()

        with patch(
            "app.tasks.send_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            send_broadcast_chunk_task([str(email.id)])

        mock_provider.return_value.send_batch.assert_not_called()

        real_db.expire_all()
        updated = real_db.query(Email).filter(Email.id == email.id).first()
        assert updated.status == EmailStatus.SUPPRESSED

    def test_per_message_error_only_affects_that_recipient(self, real_db):
        project_id = uuid4()
        ok_email = _make_email_with_payload(real_db, project_id, "ok@example.com")
        bad_email = _make_email_with_payload(real_db, project_id, "bad@example.com")

        with patch(
            "app.tasks.send_broadcast_chunk_task.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.send_batch.return_value = [
                EmailSendResult(ok=True, provider_message_id="pm-ok"),
                EmailSendResult(
                    ok=False, error_code="300", error_message="bad address"
                ),
            ]
            send_broadcast_chunk_task([str(ok_email.id), str(bad_email.id)])

        real_db.expire_all()
        ok_updated = real_db.query(Email).filter(Email.id == ok_email.id).first()
        bad_updated = real_db.query(Email).filter(Email.id == bad_email.id).first()
        assert ok_updated.status == EmailStatus.SENT
        assert bad_updated.status == EmailStatus.FAILED
        assert bad_updated.error_message == "bad address"
