"""Integration coverage: a SubscriptionChange webhook results in both the
EmailEvent/status write (via EmailLifecycleService) and the suppression row,
and HandleSubscriptionChangeCommand is invoked only for unsubscribe/
reactivation event types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.commands.providers.process_delivery_events_command import (
    ProcessDeliveryEventsCommand,
)
from app.constants.email import EmailStatus
from app.models.email import Email
from app.models.email_suppression import EmailSuppression
from app.providers.base import EmailEvent


def _make_email(db, project_id, provider_message_id):
    email = Email(
        id=uuid4(),
        project_id=project_id,
        from_email="sender@example.com",
        to_email="recipient@example.com",
        subject="Test",
        body="Body",
        status=EmailStatus.SENT,
        provider="postmark",
        provider_message_id=provider_message_id,
    )
    db.add(email)
    db.commit()
    return email


class TestUnsubscribeIntegration:
    def test_subscription_change_writes_status_and_suppression(self, db):
        project_id = uuid4()
        email = _make_email(db, project_id, "pm-unsub-1")

        mock_provider = MagicMock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = True
        mock_provider.parse_webhook.return_value = [
            EmailEvent(
                provider_name="postmark",
                provider_message_id="pm-unsub-1",
                type="unsubscribed",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={
                    "MessageID": "pm-unsub-1",
                    "SuppressSending": True,
                    "Origin": "Recipient",
                },
            )
        ]

        with patch(
            "app.commands.providers.handle_subscription_change_command.NatsEventPublisher"
        ):
            result = ProcessDeliveryEventsCommand(db).execute(
                provider=mock_provider,
                body_bytes=b"{}",
                payload={},
                headers={},
            )

        assert result["events_processed"] == 1

        db.expire_all()
        updated_email = db.query(Email).filter(Email.id == email.id).first()
        assert updated_email.status == EmailStatus.UNSUBSCRIBED

        suppression = (
            db.query(EmailSuppression)
            .filter(
                EmailSuppression.project_id == project_id,
                EmailSuppression.email == "recipient@example.com",
            )
            .first()
        )
        assert suppression is not None

    def test_non_subscription_change_event_does_not_invoke_handler(self, db):
        project_id = uuid4()
        _make_email(db, project_id, "pm-delivered-1")

        mock_provider = MagicMock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = True
        mock_provider.parse_webhook.return_value = [
            EmailEvent(
                provider_name="postmark",
                provider_message_id="pm-delivered-1",
                type="delivered",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={"MessageID": "pm-delivered-1"},
            )
        ]

        with patch(
            "app.commands.providers.process_delivery_events_command.HandleSubscriptionChangeCommand"
        ) as MockHandler:
            ProcessDeliveryEventsCommand(db).execute(
                provider=mock_provider,
                body_bytes=b"{}",
                payload={},
                headers={},
            )

        MockHandler.assert_not_called()
