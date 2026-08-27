"""Unit tests for EmailLifecycleService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
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


class TestRecordWebhookEventEngagementOutcome:
    """First-open/first-click are recorded via an atomic conditional update
    on the repo, independent of status transitions — see WebhookOutcome."""

    def test_opened_event_calls_set_first_opened_at(self):
        service, repo = _make_service()
        repo.set_first_opened_at.return_value = True
        email = _make_email(status=EmailStatus.SENT)
        occurred_at = datetime.now(timezone.utc)

        outcome = service.record_webhook_event(
            email=email,
            event_type="opened",
            occurred_at=occurred_at,
            raw_payload={},
        )

        repo.set_first_opened_at.assert_called_once_with(email.id, occurred_at)
        repo.set_first_clicked_at.assert_not_called()
        assert outcome.first_opened is True
        assert outcome.first_clicked is False

    def test_clicked_event_calls_set_first_clicked_at(self):
        service, repo = _make_service()
        repo.set_first_clicked_at.return_value = True
        email = _make_email(status=EmailStatus.SENT)
        occurred_at = datetime.now(timezone.utc)

        outcome = service.record_webhook_event(
            email=email,
            event_type="clicked",
            occurred_at=occurred_at,
            raw_payload={},
        )

        repo.set_first_clicked_at.assert_called_once_with(email.id, occurred_at)
        repo.set_first_opened_at.assert_not_called()
        assert outcome.first_clicked is True
        assert outcome.first_opened is False

    def test_repeated_click_reports_first_clicked_false(self):
        """Duplicate webhook delivery: the atomic repo call reports it was
        not first, and the outcome reflects that — no double-count."""
        service, repo = _make_service()
        repo.set_first_clicked_at.return_value = False
        email = _make_email(status=EmailStatus.CLICKED)

        outcome = service.record_webhook_event(
            email=email,
            event_type="clicked",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        assert outcome.first_clicked is False

    def test_click_before_open_does_not_regress_status_but_records_open(self):
        """Click already advanced status to CLICKED; a later, out-of-order
        'opened' webhook must not move status backward, but must still
        record first-open — status ordering never discards engagement
        evidence."""
        service, repo = _make_service()
        repo.set_first_opened_at.return_value = True
        email = _make_email(status=EmailStatus.CLICKED)

        outcome = service.record_webhook_event(
            email=email,
            event_type="opened",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        assert outcome.first_opened is True
        assert outcome.status_changed_to is None
        repo.update_email.assert_not_called()

    def test_open_before_click_advances_status_normally(self):
        service, repo = _make_service()
        repo.set_first_clicked_at.return_value = True
        email = _make_email(status=EmailStatus.OPENED)

        outcome = service.record_webhook_event(
            email=email,
            event_type="clicked",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        assert outcome.first_clicked is True
        assert outcome.status_changed_to == EmailStatus.CLICKED
        repo.update_email.assert_called_once()

    def test_engagement_recorded_even_after_terminal_status(self):
        """A terminal status (e.g. bounced) blocks status writes, but an
        out-of-order open/click webhook still records its timestamp — status
        ordering must not discard evidence of engagement."""
        service, repo = _make_service()
        repo.set_first_clicked_at.return_value = True
        email = _make_email(status=EmailStatus.BOUNCED)

        outcome = service.record_webhook_event(
            email=email,
            event_type="clicked",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        assert outcome.first_clicked is True
        assert outcome.status_changed_to is None
        repo.update_email.assert_not_called()

    def test_click_does_not_synthesize_open(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        service.record_webhook_event(
            email=email,
            event_type="clicked",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.set_first_opened_at.assert_not_called()

    def test_unrelated_event_does_not_touch_engagement_timestamps(self):
        service, repo = _make_service()
        email = _make_email(status=EmailStatus.SENT)

        outcome = service.record_webhook_event(
            email=email,
            event_type="delivered",
            occurred_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        repo.set_first_opened_at.assert_not_called()
        repo.set_first_clicked_at.assert_not_called()
        assert outcome.first_opened is False
        assert outcome.first_clicked is False
