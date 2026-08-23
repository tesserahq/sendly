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
        EmailStatus.UNSUBSCRIBED,
        EmailStatus.SUPPRESSED,
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
    ) -> Optional[str]:
        """
        Persist one webhook event row and advance Email.status if appropriate.

        Unknown event types are accepted — the event row is written but
        Email.status is left unchanged (forward-compatible with new provider events).
        Terminal statuses (bounced, complained, dropped, failed) are never overwritten.

        Returns the new Email.status if this event actually changed it, or
        None if the event was a no-op (unknown type, already at that status,
        or the email was already terminal) — callers use this to tell a
        genuine first-time transition apart from a duplicate/retried webhook
        delivery for the same event.
        """
        self._create_event(
            email_id=email.id,
            event_type=event_type,
            occurred_at=occurred_at,
            details=raw_payload,
        )
        return self._advance_status_and_opened_at(email, event_type, occurred_at)

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

    def record_send_suppressed(
        self,
        *,
        email: Email,
        reason: Optional[str] = None,
        suppressed_at: Optional[datetime] = None,
    ) -> Email:
        """
        Mark an email SUPPRESSED (terminal) and emit a 'suppressed' event.

        Used when a recipient is found to be suppressed (unsubscribed) at
        send time, distinct from a provider failure.

        Returns the updated Email.
        """
        now = suppressed_at or datetime.now(timezone.utc)
        updated = self._repo.update_email(
            email.id,
            EmailUpdate(status=EmailStatus.SUPPRESSED),
        )
        self._create_event(
            email_id=email.id,
            event_type="suppressed",
            occurred_at=now,
            details={"reason": reason},
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

    def _advance_status_and_opened_at(
        self, email: Email, event_type: str, occurred_at: datetime
    ) -> Optional[str]:
        new_status = _WEBHOOK_EVENT_TO_STATUS.get(event_type)
        if new_status is not None and (
            email.status in _TERMINAL_STATUSES or new_status == email.status
        ):
            new_status = None  # no-op / already terminal; never overwrite

        fields: dict[str, Any] = {}
        if new_status is not None:
            fields["status"] = new_status
        if event_type == "opened" and email.opened_at is None:
            fields["opened_at"] = occurred_at

        if not fields:
            return None
        self._repo.update_email(email.id, EmailUpdate(**fields))
        return new_status
