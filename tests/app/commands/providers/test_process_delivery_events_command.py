"""Tests for the ProcessDeliveryEventsCommand."""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import Mock

from app.commands.providers.process_delivery_events_command import (
    ProcessDeliveryEventsCommand,
)
from app.models.email import Email
from app.constants.email import EmailStatus
from app.providers.base import EmailEvent


class TestProcessDeliveryEventsCommand:
    """Test suite for ProcessDeliveryEventsCommand."""

    def test_execute_processes_events_successfully(self, db):
        """Command processes webhook events and creates email events."""
        # Create an email with a known provider_message_id
        provider_msg_id = "test-message-123"
        email = Email(
            id=uuid4(),
            from_email="sender@example.com",
            to_email="recipient@example.com",
            subject="Test Email",
            body="Test body",
            status=EmailStatus.SENT,
            provider="postmark",
            provider_message_id=provider_msg_id,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(email)
        db.commit()

        # Mock provider
        mock_provider = Mock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = True
        mock_provider.parse_webhook.return_value = [
            EmailEvent(
                provider_name="postmark",
                provider_message_id=provider_msg_id,
                type="delivered",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={"RecordType": "Delivery", "MessageID": provider_msg_id},
            )
        ]

        # Execute command
        command = ProcessDeliveryEventsCommand(db)
        result = command.execute(
            provider=mock_provider,
            body_bytes=b'{"test": "data"}',
            payload={"RecordType": "Delivery", "MessageID": provider_msg_id},
            headers={"Content-Type": "application/json"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["provider"] == "postmark"
        assert result["events_received"] == 1
        assert result["events_processed"] == 1
        assert result["events_failed"] == 0
        assert result["failures"] is None

        # Verify provider methods were called
        mock_provider.verify_webhook.assert_called_once()
        mock_provider.parse_webhook.assert_called_once()

    def test_execute_handles_missing_email(self, db):
        """Command handles events for emails that don't exist."""
        # Mock provider
        mock_provider = Mock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = True
        mock_provider.parse_webhook.return_value = [
            EmailEvent(
                provider_name="postmark",
                provider_message_id="non-existent-message-id",
                type="delivered",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={"RecordType": "Delivery"},
            )
        ]

        # Execute command
        command = ProcessDeliveryEventsCommand(db)
        result = command.execute(
            provider=mock_provider,
            body_bytes=b'{"test": "data"}',
            payload={"RecordType": "Delivery"},
            headers={"Content-Type": "application/json"},
        )

        # Verify result shows failure
        assert result["status"] == "partial_failure"
        assert result["events_received"] == 1
        assert result["events_processed"] == 0
        assert result["events_failed"] == 1
        assert result["failures"] is not None
        assert len(result["failures"]) == 1
        assert "Email not found" in result["failures"][0]["error"]

    def test_execute_fails_on_invalid_signature(self, db):
        """Command rejects webhooks with invalid signatures."""
        from fastapi import HTTPException

        # Mock provider that fails verification
        mock_provider = Mock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = False

        # Execute command and expect exception
        command = ProcessDeliveryEventsCommand(db)
        with pytest.raises(HTTPException) as exc_info:
            command.execute(
                provider=mock_provider,
                body_bytes=b'{"test": "data"}',
                payload={"test": "data"},
                headers={"Content-Type": "application/json"},
            )

        assert exc_info.value.status_code == 401
        assert "signature verification failed" in exc_info.value.detail.lower()

    def test_execute_processes_multiple_events(self, db):
        """Command processes multiple events in a single webhook."""
        # Create two emails
        provider_msg_id_1 = "msg-001"
        provider_msg_id_2 = "msg-002"

        for msg_id in [provider_msg_id_1, provider_msg_id_2]:
            email = Email(
                id=uuid4(),
                from_email="sender@example.com",
                to_email=f"recipient-{msg_id}@example.com",
                subject="Test Email",
                body="Test body",
                status=EmailStatus.SENT,
                provider="postmark",
                provider_message_id=msg_id,
                sent_at=datetime.now(timezone.utc),
            )
            db.add(email)
        db.commit()

        # Mock provider with multiple events
        mock_provider = Mock()
        mock_provider.provider_id = "postmark"
        mock_provider.verify_webhook.return_value = True
        mock_provider.parse_webhook.return_value = [
            EmailEvent(
                provider_name="postmark",
                provider_message_id=provider_msg_id_1,
                type="delivered",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={"MessageID": provider_msg_id_1},
            ),
            EmailEvent(
                provider_name="postmark",
                provider_message_id=provider_msg_id_2,
                type="opened",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={"MessageID": provider_msg_id_2},
            ),
        ]

        # Execute command
        command = ProcessDeliveryEventsCommand(db)
        result = command.execute(
            provider=mock_provider,
            body_bytes=b'{"test": "data"}',
            payload={"events": []},
            headers={"Content-Type": "application/json"},
        )

        # Verify both events were processed
        assert result["status"] == "success"
        assert result["events_received"] == 2
        assert result["events_processed"] == 2
        assert result["events_failed"] == 0
