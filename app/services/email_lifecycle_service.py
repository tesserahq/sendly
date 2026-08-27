"""Single authority for all writes to Email.status and EmailEvent rows."""

from __future__ import annotations

from dataclasses import dataclass
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

# Forward-progression ranks for the non-terminal happy-path statuses. A
# webhook that would move status backward within this set (e.g. an "opened"
# event arriving after a "clicked" one already advanced status) is ignored
# for status purposes — but engagement timestamps are still recorded
# independently (see record_webhook_event), so out-of-order delivery never
# discards evidence of engagement, only a status regression.
_PROGRESSION_RANK: dict[str, int] = {
    EmailStatus.SENT: 1,
    EmailStatus.DELIVERED: 2,
    EmailStatus.OPENED: 3,
    EmailStatus.CLICKED: 4,
}


@dataclass(frozen=True)
class WebhookOutcome:
    """Result of recording one webhook event.

    status_changed_to is the new Email.status if this event actually
    advanced it, or None for a no-op (unknown type, no forward progress, or
    an already-terminal email). first_opened/first_clicked are True only on
    the webhook delivery that actually transitioned the corresponding
    timestamp from null — computed via an atomic conditional update, so
    duplicate/concurrent webhook deliveries for the same email produce the
    flag exactly once. Callers use these to decide whether to increment
    batch-level counters without re-implementing this idempotency.
    """

    status_changed_to: Optional[str] = None
    first_opened: bool = False
    first_clicked: bool = False


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
    ) -> WebhookOutcome:
        """
        Persist one webhook event row, atomically record first-open/
        first-click if this event is one, and advance Email.status if
        appropriate.

        Unknown event types are accepted — the event row is written but
        Email.status is left unchanged (forward-compatible with new provider
        events). Terminal statuses (bounced, complained, dropped, failed)
        are never overwritten, and status never regresses within the
        happy-path progression (sent -> delivered -> opened -> clicked).

        First-open/first-click are recorded independently of status: an
        out-of-order webhook that doesn't change status still records its
        engagement timestamp, and a click never synthesizes an open.

        Returns a WebhookOutcome describing what actually changed — callers
        use this to tell a genuine first-time transition/occurrence apart
        from a duplicate/retried or out-of-order webhook delivery.
        """
        self._create_event(
            email_id=email.id,
            event_type=event_type,
            occurred_at=occurred_at,
            details=raw_payload,
        )

        first_opened = False
        first_clicked = False
        if event_type == "opened":
            first_opened = self._repo.set_first_opened_at(email.id, occurred_at)
        elif event_type == "clicked":
            first_clicked = self._repo.set_first_clicked_at(email.id, occurred_at)

        new_status = self._advance_status(email, event_type)

        return WebhookOutcome(
            status_changed_to=new_status,
            first_opened=first_opened,
            first_clicked=first_clicked,
        )

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

    def _advance_status(self, email: Email, event_type: str) -> Optional[str]:
        new_status = _WEBHOOK_EVENT_TO_STATUS.get(event_type)
        if new_status is None:
            return None
        if email.status in _TERMINAL_STATUSES or new_status == email.status:
            return None  # already terminal / no-op; never overwrite

        old_rank = _PROGRESSION_RANK.get(email.status)
        new_rank = _PROGRESSION_RANK.get(new_status)
        if old_rank is not None and new_rank is not None and new_rank <= old_rank:
            return None  # out-of-order webhook; don't regress status

        self._repo.update_email(email.id, EmailUpdate(status=new_status))
        return new_status
