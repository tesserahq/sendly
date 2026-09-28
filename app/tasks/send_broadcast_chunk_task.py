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
from uuid import UUID

from app.core.celery_app import celery_app
from app.db import session_scope
from app.providers.base import Attachment, EmailCreateRequest
from app.providers.registry import get_default_provider
from app.repositories.broadcast_repository import BroadcastRepository
from app.repositories.email_delivery_payload_repository import (
    EmailDeliveryPayloadRepository,
)
from app.repositories.email_repository import EmailRepository
from app.repositories.email_send_outbox_repository import EmailSendOutboxRepository
from app.repositories.suppression_repository import SuppressionRepository
from app.services.email_lifecycle_service import EmailLifecycleService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.send_broadcast_chunk_task", bind=True, max_retries=3)
def send_broadcast_chunk_task(self, email_ids: list[str]) -> None:
    try:
        with session_scope() as db:
            _send_chunk(db, [UUID(i) for i in email_ids])
    except Exception as exc:
        logger.exception(
            "send_broadcast_chunk_task transport failure; retrying whole chunk"
        )
        raise self.retry(exc=exc, countdown=30)


def _send_chunk(db, email_ids: list[UUID]) -> None:
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
    email_ids_to_send = [email.id for email, _payload in to_send]

    # Local terminal outcomes do not depend on Postmark and can be finalized now.
    outbox_repo.mark_processed(handled_email_ids)

    if requests:
        # commit: provider_input_ready. Release the connection before Postmark.
        # PRD 0003's durable claim state will make this boundary exclusive.
        db.commit()
        provider = get_default_provider()
        results = provider.send_batch(requests)
        reloaded_emails = {
            email.id: email for email in email_repo.get_emails_by_ids(email_ids_to_send)
        }
        for email_id, result in zip(email_ids_to_send, results):
            email = reloaded_emails[email_id]
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

        outbox_repo.mark_processed(email_ids_to_send)

    if handled_email_ids:
        # Reload after an early commit rather than relying on expired instances.
        handled_emails = {
            email.id: email for email in email_repo.get_emails_by_ids(handled_email_ids)
        }
        broadcast_repo = BroadcastRepository(db)
        batch_ids = {
            email.batch_id for email in handled_emails.values() if email.batch_id
        }
        for batch_id in batch_ids:
            batch = broadcast_repo.get_batch_by_batch_id(batch_id)
            if batch is None:
                continue
            pending_send_count = outbox_repo.count_pending_for_batch(batch_id)
            broadcast_repo.maybe_mark_finished(batch.id, pending_send_count)
