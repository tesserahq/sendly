"""Prepare stage: renders each non-suppressed recipient's content and creates
their Email row, immutable delivery payload, and outbox entry.

A per-recipient rendering failure is logged and skipped — it never blocks the
rest of the chunk (a recipient suppressed since acceptance is treated the
same way: marked prepared, no Email row, no render attempted).
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from app.config import get_settings
from app.constants.email import EmailStatus
from app.core.celery_app import celery_app
from app.providers.base import EmailCreateRequest
from app.providers.registry import get_default_provider
from app.repositories.broadcast_repository import BroadcastRepository
from app.repositories.email_delivery_payload_repository import (
    EmailDeliveryPayloadRepository,
)
from app.repositories.email_repository import EmailRepository
from app.repositories.email_send_outbox_repository import EmailSendOutboxRepository
from app.repositories.suppression_repository import SuppressionRepository
from app.schemas.broadcast import ContentSpec
from app.schemas.email import EmailCreate
from app.services.broadcast_outbox_publisher import BroadcastOutboxPublisher
from app.services.email_rendering_service import (
    EmailRenderingService,
    MissingFieldError,
    TemplateNotFoundError,
    TemplateSyntaxError,
)
from app.utils.db.db_session_helper import db_session

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.prepare_broadcast_chunk_task")
def prepare_broadcast_chunk_task(
    broadcast_batch_id: str, recipient_ids: List[str]
) -> None:
    with db_session() as db:
        _prepare_chunk(db, UUID(broadcast_batch_id), [UUID(i) for i in recipient_ids])


def _prepare_chunk(db, broadcast_batch_id: UUID, recipient_ids: List[UUID]) -> None:
    broadcast_repo = BroadcastRepository(db)
    suppression_repo = SuppressionRepository(db)
    email_repo = EmailRepository(db)
    payload_repo = EmailDeliveryPayloadRepository(db)
    outbox_repo = EmailSendOutboxRepository(db)
    rendering = EmailRenderingService(db)
    settings = get_settings()

    batch = broadcast_repo.get_batch_by_id(broadcast_batch_id)
    if batch is None:
        logger.error(
            "prepare_broadcast_chunk_task: batch %s not found", broadcast_batch_id
        )
        return

    recipients = broadcast_repo.get_recipients_by_ids(recipient_ids)
    if not recipients:
        return

    content_spec = ContentSpec.model_validate(batch.content_spec)
    # Recheck suppression: a recipient suppressed between acceptance and this
    # task still gets skipped, even though it wasn't flagged suppressed at
    # accept time.
    still_suppressed = suppression_repo.is_suppressed_bulk(
        batch.project_id, [recipient.email for recipient in recipients]
    )

    prepared_ids: List[UUID] = []
    created_email_ids: List[UUID] = []
    message_stream = settings.postmark_broadcast_stream_id or None

    for recipient in recipients:
        prepared_ids.append(recipient.id)

        if recipient.email in still_suppressed:
            continue

        template_variables = {
            **content_spec.template_variables,
            **(recipient.attributes or {}),
            "first_name": recipient.first_name,
            "last_name": recipient.last_name,
        }
        req = EmailCreateRequest(
            project_id=batch.project_id,
            from_email=content_spec.from_email,
            subject=content_spec.subject,
            html=content_spec.html,
            text=content_spec.text,
            attachments=content_spec.attachments,
            to=[recipient.email],
            template_id=content_spec.template_id,
            template_alias=content_spec.template_alias,
            template_variables=template_variables,
            custom_headers=content_spec.custom_headers,
            message_stream=message_stream,
        )

        try:
            rendered = rendering.resolve(req)
        except (MissingFieldError, TemplateNotFoundError, TemplateSyntaxError) as e:
            logger.warning(
                "Skipping recipient %s in batch %s: rendering failed: %s",
                recipient.email,
                broadcast_batch_id,
                e,
            )
            continue

        provider = get_default_provider()
        email = email_repo.create_email(
            EmailCreate(
                project_id=batch.project_id,
                provider=provider.provider_id,
                from_email=rendered.from_email,
                to_email=recipient.email,
                subject=rendered.subject,
                body=rendered.html,
                status=EmailStatus.QUEUED,
                batch_id=batch.batch_id,
                tags=content_spec.tags,
                metadata_=content_spec.metadata,
            )
        )
        payload_repo.create_payload(
            email_id=email.id,
            from_email=rendered.from_email,
            to_email=recipient.email,
            subject=rendered.subject,
            html=rendered.html,
            text=content_spec.text,
            attachments=[a.model_dump() for a in content_spec.attachments],
            custom_headers=content_spec.custom_headers,
            message_stream=message_stream,
        )
        outbox_repo.create_entry(email_id=email.id)
        created_email_ids.append(email.id)

    broadcast_repo.mark_recipients_prepared(prepared_ids)

    if created_email_ids:
        # Fast path: dispatch the send stage synchronously, after commit.
        BroadcastOutboxPublisher(db).dispatch(created_email_ids)
