"""Unit tests for HandleSubscriptionChangeCommand: mocked SuppressionRepository
and NatsEventPublisher — no DB, no NATS."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.commands.providers.handle_subscription_change_command import (
    HandleSubscriptionChangeCommand,
)
from app.models.email import Email


def _make_email(**overrides):
    defaults = dict(
        id=uuid4(),
        project_id=uuid4(),
        from_email="sender@example.com",
        to_email="recipient@example.com",
        subject="Test",
        body="Body",
        status="sent",
        provider="postmark",
    )
    defaults.update(overrides)
    return Email(**defaults)


def _make_command():
    suppression_repo = MagicMock()
    nats_publisher = MagicMock()
    command = HandleSubscriptionChangeCommand(
        db=MagicMock(), nats_publisher=nats_publisher
    )
    command.suppression_repo = suppression_repo
    return command, suppression_repo, nats_publisher


class TestRecipientUnsubscribe:
    def test_upserts_suppression_and_publishes_nats_event(self):
        command, suppression_repo, nats_publisher = _make_command()
        email = _make_email()

        command.execute(
            email=email,
            raw_payload={
                "MessageID": "pm-123",
                "SuppressSending": True,
                "Origin": "Recipient",
                "ChangedAt": "2026-01-01T00:00:00Z",
            },
        )

        suppression_repo.create_or_update_suppression.assert_called_once()
        call_kwargs = suppression_repo.create_or_update_suppression.call_args.kwargs
        assert call_kwargs["project_id"] == email.project_id
        assert call_kwargs["email"] == email.to_email

        nats_publisher.publish_sync.assert_called_once()
        event, subject = nats_publisher.publish_sync.call_args.args
        assert subject == event.event_type
        assert event.event_data["id"] == str(email.id)


class TestReactivation:
    def test_removes_suppression_and_does_not_publish(self):
        command, suppression_repo, nats_publisher = _make_command()
        email = _make_email()

        command.execute(
            email=email,
            raw_payload={
                "MessageID": "pm-123",
                "SuppressSending": False,
                "Origin": "Recipient",
            },
        )

        suppression_repo.remove_suppression.assert_called_once_with(
            project_id=email.project_id, email=email.to_email
        )
        nats_publisher.publish_sync.assert_not_called()


class TestNonRecipientOriginated:
    def test_suppresses_but_does_not_publish_for_non_recipient_origin(self):
        command, suppression_repo, nats_publisher = _make_command()
        email = _make_email()

        command.execute(
            email=email,
            raw_payload={
                "MessageID": "pm-123",
                "SuppressSending": True,
                "Origin": "Admin",
            },
        )

        suppression_repo.create_or_update_suppression.assert_called_once()
        nats_publisher.publish_sync.assert_not_called()


class TestNullMessageId:
    def test_skips_mutation_and_does_not_raise(self):
        command, suppression_repo, nats_publisher = _make_command()
        email = _make_email()

        command.execute(
            email=email,
            raw_payload={"MessageID": None, "SuppressSending": True},
        )

        suppression_repo.create_or_update_suppression.assert_not_called()
        suppression_repo.remove_suppression.assert_not_called()
        nats_publisher.publish_sync.assert_not_called()

    def test_skips_mutation_when_email_unresolvable(self):
        command, suppression_repo, nats_publisher = _make_command()

        command.execute(
            email=None,
            raw_payload={"MessageID": "pm-123", "SuppressSending": True},
        )

        suppression_repo.create_or_update_suppression.assert_not_called()
        nats_publisher.publish_sync.assert_not_called()
