"""Send stage: sends a chunk's immutable delivery payloads via Postmark's Bulk
API in one HTTP call, then records each recipient's outcome individually.

A recipient suppressed since acceptance is recorded as `suppressed` (not
attempted, not a failure). If the HTTP call itself fails at the transport
level (timeout, connection error, provider 5xx), the whole chunk is retried
as a unit — accepting a small risk of double-sending a recipient whose
message actually made it to Postmark before the connection dropped, since the
Bulk API has no per-message idempotency key to check against first.
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from app.core.celery_app import celery_app
from app.providers.base import Attachment, EmailCreateRequest
from app.providers.registry import get_default_provider
from app.repositories.email_delivery_payload_repository import (
    EmailDeliveryPayloadRepository,
)
from app.repositories.email_repository import EmailRepository
from app.repositories.email_send_outbox_repository import EmailSendOutboxRepository
from app.repositories.suppression_repository import SuppressionRepository
from app.services.email_lifecycle_service import EmailLifecycleService
from app.utils.db.db_session_helper import db_session

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.send_broadcast_chunk_task", bind=True, max_retries=3)
def send_broadcast_chunk_task(self, email_ids: List[str]) -> None:
    try:
        with db_session() as db:
            _send_chunk(db, [UUID(i) for i in email_ids])
    except Exception as exc:
        logger.exception(
            "send_broadcast_chunk_task transport failure; retrying whole chunk"
        )
        raise self.retry(exc=exc, countdown=30)


def _send_chunk(db, email_ids: List[UUID]) -> None:
    email_repo = EmailRepository(db)
    payload_repo = EmailDeliveryPayloadRepository(db)
    outbox_repo = EmailSendOutboxRepository(db)
    suppression_repo = SuppressionRepository(db)
    lifecycle = EmailLifecycleService(email_repo)

    emails = {email.id: email for email in email_repo.get_emails_by_ids(email_ids)}
    payloads = {
        payload.email_id: payload
        for payload in payload_repo.get_by_email_ids(list(emails.keys()))
    }
    # One bulk suppression lookup for the whole chunk, not one query per
    # recipient — matches the pattern already used in SendBroadcastCommand
    # and prepare_broadcast_chunk_task.
    suppressed = suppression_repo.is_suppressed_bulk(
        # All emails in a chunk share one project_id — the batch's.
        next(iter(emails.values())).project_id if emails else None,
        [email.to_email for email in emails.values()],
    )

    to_send = []
    handled_email_ids = []
    for email_id, email in emails.items():
        payload = payloads.get(email_id)
        if payload is None:
            # Data inconsistency (e.g. a partially-completed prepare chunk):
            # record it as a failure rather than silently marking the outbox
            # entry processed with the email stuck at `queued` forever.
            logger.error(
                "send_broadcast_chunk_task: no delivery payload for email %s; "
                "recording as failed",
                email_id,
            )
            lifecycle.record_send_failure(
                email=email, error_message="Missing delivery payload"
            )
            handled_email_ids.append(email_id)
            continue
        if email.to_email in suppressed:
            lifecycle.record_send_suppressed(
                email=email, reason="unsubscribed_before_send"
            )
            handled_email_ids.append(email_id)
            continue
        to_send.append((email, payload))

    if to_send:
        provider = get_default_provider()
        requests = [
            EmailCreateRequest(
                project_id=email.project_id,
                from_email=payload.from_email,
                reply_to=payload.reply_to,
                subject=payload.subject,
                html=payload.html,
                text=payload.text,
                attachments=[Attachment(**a) for a in (payload.attachments or [])],
                to=[payload.to_email],
                custom_headers=payload.custom_headers or {},
                message_stream=payload.message_stream,
            )
            for email, payload in to_send
        ]
        results = provider.send_batch(requests)
        for (email, _payload), result in zip(to_send, results):
            if result.ok:
                lifecycle.record_send_success(
                    email=email, provider_message_id=result.provider_message_id
                )
            else:
                lifecycle.record_send_failure(
                    email=email,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
            handled_email_ids.append(email.id)

    # Only mark entries whose email actually got a terminal outcome recorded
    # above — never blanket-mark every id we merely looked up.
    outbox_repo.mark_processed(handled_email_ids)
