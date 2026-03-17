"""Unit tests for EmailLifecycleService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from app.constants.email import EmailStatus
from app.models.email import Email
from app.services.email_lifecycle_service import EmailLifecycleService


def _make_email(status: str = EmailStatus.SENT) -> Email:
    email = Email(
        id=uuid4(),
        from_email="sender@example.com",
        to_email="recipient@example.com",
        subject="Test",
        body="Body",
        status=status,
        provider="postmark",
    )
    return email


def _make_service() -> tuple[EmailLifecycleService, MagicMock]:
    repo = MagicMock()
    repo.update_email.return_value = MagicMock()
    service = EmailLifecycleService(repo)
    return service, repo


class TestRecordSendSuccess:
    def test_updates_status_to_sent(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.QUEUED)

        service.record_send_success(email=email, provider_message_id="msg-123")

        repo.update_email.assert_called_once()
        update_arg = repo.update_email.call_args[0][1]
        assert update_arg.status == EmailStatus.SENT
        assert update_arg.provider_message_id == "msg-123"

    def test_emits_sent_event(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.QUEUED)

        service.record_send_success(email=email, provider_message_id="msg-123")

        repo.create_email_event.assert_called_once()
        event_arg = repo.create_email_event.call_args[0][0]
        assert event_arg.event_type == "sent"
        assert event_arg.email_id == email.id

    def test_returns_updated_email(self):
        service, repo = _make_service()
        updated = MagicMock()
        repo.update_email.return_value = updated
        email = _make_email(status=EmailStatus.QUEUED)

        result = service.record_send_success(email=email)

        assert result is updated


class TestRecordSendFailure:
    def test_updates_status_to_failed(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.QUEUED)

        service.record_send_failure(
            email=email, error_code="429", error_message="rate limited"
        )

        repo.update_email.assert_called_once()
        update_arg = repo.update_email.call_args[0][1]
        assert update_arg.status == EmailStatus.FAILED
        assert update_arg.error_message == "rate limited"

    def test_emits_failed_event_with_details(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.QUEUED)

        service.record_send_failure(
            email=email, error_code="429", error_message="rate limited"
        )

        repo.create_email_event.assert_called_once()
        event_arg = repo.create_email_event.call_args[0][0]
        assert event_arg.event_type == "failed"
        assert event_arg.details["error_code"] == "429"
        assert event_arg.details["error_message"] == "rate limited"


class TestRecordWebhookEvent:
    def test_advances_status_on_delivery(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type="delivered",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.update_email.assert_called_once()
        update_arg = repo.update_email.call_args[0][1]
        assert update_arg.status == EmailStatus.DELIVERED

    def test_always_writes_event_row(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type="delivered",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={"key": "value"},
        )

        repo.create_email_event.assert_called_once()
        event_arg = repo.create_email_event.call_args[0][0]
        assert event_arg.event_type == "delivered"
        assert event_arg.details == {"key": "value"}

    def test_does_not_overwrite_terminal_status(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.BOUNCED)

        service.record_webhook_event(
            email=email,
            event_type="delivered",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        # Event row written but status NOT updated
        repo.create_email_event.assert_called_once()
        repo.update_email.assert_not_called()

    def test_all_terminal_statuses_are_protected(self):
        for terminal in (
            EmailStatus.BOUNCED,
            EmailStatus.COMPLAINED,
            EmailStatus.DROPPED,
            EmailStatus.FAILED,
        ):
            service, repo = _make_service()
            email = _make_email(status=terminal)

            service.record_webhook_event(
                email=email,
                event_type="delivered",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={},
            )

            repo.update_email.assert_not_called(), f"Status {terminal} was overwritten"

    def test_unknown_event_type_writes_event_but_skips_status(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type="some_future_provider_event",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.create_email_event.assert_called_once()
        repo.update_email.assert_not_called()

    def test_noop_when_status_unchanged(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type="sent",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.create_email_event.assert_called_once()
        repo.update_email.assert_not_called()

    @pytest.mark.parametrize(
        "event_type,expected_status",
        [
            ("delivered", EmailStatus.DELIVERED),
            ("opened", EmailStatus.OPENED),
            ("clicked", EmailStatus.CLICKED),
            ("bounced", EmailStatus.BOUNCED),
            ("complained", EmailStatus.COMPLAINED),
            ("dropped", EmailStatus.DROPPED),
            ("deferred", EmailStatus.DEFERRED),
            ("spam", EmailStatus.COMPLAINED),
            ("unsubscribed", EmailStatus.UNSUBSCRIBED),
        ],
    )
    def test_event_to_status_mapping(self, event_type, expected_status):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.update_email.assert_called_once()
        update_arg = repo.update_email.call_args[0][1]
        assert update_arg.status == expected_status
