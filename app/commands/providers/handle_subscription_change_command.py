"""Reacts to a Postmark SubscriptionChange webhook (unsubscribe/reactivation).

Scoped to suppression-table writes and NATS publishing only. Email.status/
EmailEvent writes remain EmailLifecycleService's documented single
responsibility and are already handled by ProcessDeliveryEventsCommand before
this command runs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from tessera_sdk.infra.events import NatsEventPublisher

from app.events.email_events import build_email_unsubscribed_event
from app.models.email import Email
from app.repositories.suppression_repository import SuppressionRepository

logger = logging.getLogger(__name__)


class HandleSubscriptionChangeCommand:
    def __init__(
        self, db: Session, nats_publisher: Optional[NatsEventPublisher] = None
    ):
        self.db = db
        self.suppression_repo = SuppressionRepository(db)
        self.nats_publisher = nats_publisher or NatsEventPublisher()

    def execute(self, *, email: Optional[Email], raw_payload: Dict[str, Any]) -> None:
        message_id = raw_payload.get("MessageID") or raw_payload.get("MessageId")

        if email is None or not message_id:
            # A null-MessageID subscription event can't be safely assigned to a
            # project with only the global stream configured — log for operations
            # and skip; do not mutate a project suppression on a guess.
            logger.warning(
                "SubscriptionChange webhook has no resolvable email/MessageID; "
                "skipping suppression mutation. payload=%s",
                raw_payload,
            )
            return

        suppress_sending = bool(raw_payload.get("SuppressSending"))
        origin = raw_payload.get("Origin")
        changed_at = self._parse_changed_at(raw_payload.get("ChangedAt"))

        if suppress_sending:
            self.suppression_repo.create_or_update_suppression(
                project_id=email.project_id,
                email=email.to_email,
                unsubscribed_at=changed_at,
                source=f"postmark:{origin}" if origin else "postmark",
            )
            # Only a genuine recipient-originated unsubscribe is broadcast
            # downstream; other suppression sources (e.g. a manual/admin
            # suppression in Postmark) still get suppressed, silently.
            if origin == "Recipient":
                self._publish_unsubscribed(email)
        else:
            self.suppression_repo.remove_suppression(
                project_id=email.project_id,
                email=email.to_email,
            )

    def _publish_unsubscribed(self, email: Email) -> None:
        event = build_email_unsubscribed_event(email)
        try:
            self.nats_publisher.publish_sync(event, event.event_type)
        except Exception:
            logger.exception("Failed to publish email.unsubscribed event to NATS")

    @staticmethod
    def _parse_changed_at(value: Any) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
