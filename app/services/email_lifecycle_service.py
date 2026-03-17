"""Single authority for all writes to Email.status and EmailEvent rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.constants.email import EmailStatus
from app.models.email import Email
from app.repositories.email_repository import EmailRepository
from app.schemas.email import EmailEventCreate, EmailUpdate

# Maps inbound webhook event_type strings to their corresponding Email.status value.
# Not all event types map to a status change (unknown types are silently ignored).
_WEBHOOK_EVENT_TO_STATUS: dict[str, str] = {
    "sent": EmailStatus.SENT,
    "delivered": EmailStatus.DELIVERED,
    "opened": EmailStatus.OPENED,
    "clicked": EmailStatus.CLICKED,
    "bounced": EmailStatus.BOUNCED,
    "complained": EmailStatus.COMPLAINED,
    "dropped": EmailStatus.DROPPED,
    "deferred": EmailStatus.DEFERRED,
    "spam": EmailStatus.COMPLAINED,
    "unsubscribed": EmailStatus.UNSUBSCRIBED,
    "failed": EmailStatus.FAILED,
}

# Once an email reaches a terminal status it cannot be overwritten by
# a subsequent (potentially out-of-order) webhook event.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        EmailStatus.BOUNCED,
        EmailStatus.COMPLAINED,
        EmailStatus.DROPPED,
        EmailStatus.FAILED,
    }
)


class EmailLifecycleService:
    """
    Single authority for all writes to Email.status and EmailEvent rows.

    Callers never compute status transitions, build EmailEventCreate objects,
    or decide whether to advance status. All lifecycle logic lives here.

    Inject an EmailRepository so the service shares the caller's DB session
    and can be tested independently with a mock repo.
    """

    def __init__(self, repo: EmailRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Webhook path (ProcessDeliveryEventsCommand)
    # ------------------------------------------------------------------

    def record_webhook_event(
        self,
        *,
        email: Email,
        event_type: str,
        occurred_at: datetime,
        raw_payload: dict[str, Any],
    ) -> None:
        """
        Persist one webhook event row and advance Email.status if appropriate.

        Unknown event types are accepted — the event row is written but
        Email.status is left unchanged (forward-compatible with new provider events).
        Terminal statuses (bounced, complained, dropped, failed) are never overwritten.
        """
        self._create_event(
            email_id=email.id,
            event_type=event_type,
            occurred_at=occurred_at,
            details=raw_payload,
        )
        self._maybe_advance_status(email, event_type)

    # ------------------------------------------------------------------
    # Send path (SendEmailCommand)
    # ------------------------------------------------------------------

    def record_send_success(
        self,
        *,
        email: Email,
        sent_at: Optional[datetime] = None,
        provider_message_id: Optional[str] = None,
    ) -> Email:
        """
        Mark an email SENT and emit a 'sent' event.

        Returns the updated Email.
        """
        now = sent_at or datetime.now(timezone.utc)
        updated = self._repo.update_email(
            email.id,
            EmailUpdate(
                status=EmailStatus.SENT,
                sent_at=now,
                provider_message_id=provider_message_id,
            ),
        )
        self._create_event(
            email_id=email.id,
            event_type="sent",
            occurred_at=now,
            details={"provider_message_id": provider_message_id},
        )
        return updated

    def record_send_failure(
        self,
        *,
        email: Email,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        failed_at: Optional[datetime] = None,
    ) -> Email:
        """
        Mark an email FAILED and emit a 'failed' event.

        Returns the updated Email.
        """
        now = failed_at or datetime.now(timezone.utc)
        updated = self._repo.update_email(
            email.id,
            EmailUpdate(
                status=EmailStatus.FAILED,
                error_message=error_message,
            ),
        )
        self._create_event(
            email_id=email.id,
            event_type="failed",
            occurred_at=now,
            details={"error_code": error_code, "error_message": error_message},
        )
        return updated

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_event(
        self,
        *,
        email_id: UUID,
        event_type: str,
        occurred_at: datetime,
        details: dict[str, Any],
    ) -> None:
        self._repo.create_email_event(
            EmailEventCreate(
                email_id=email_id,
                event_type=event_type,
                event_timestamp=occurred_at,
                details=details,
            )
        )

    def _maybe_advance_status(self, email: Email, event_type: str) -> None:
        new_status = _WEBHOOK_EVENT_TO_STATUS.get(event_type)
        if new_status is None:
            return  # unknown event type — event row was written, status unchanged
        if email.status in _TERMINAL_STATUSES:
            return  # already terminal; never overwrite
        if new_status == email.status:
            return  # no-op
        self._repo.update_email(email.id, EmailUpdate(status=new_status))
