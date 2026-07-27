"""Accept stage of broadcast sending.

Does exactly one bulk suppression lookup and one transaction (batch row +
raw recipient rows) — no rendering, no Email rows here. That keeps
acceptance O(1) round-trips regardless of recipient-list size; rendering
and Email-row creation happen later, in the chunked, asynchronous prepare
stage (see app/tasks/prepare_broadcast_chunk_task.py).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.broadcast_batch import BroadcastBatch
from app.repositories.broadcast_repository import BroadcastRepository
from app.repositories.suppression_repository import SuppressionRepository
from app.schemas.broadcast import (
    BroadcastCreateRequest,
    BroadcastRecipient,
    ContentSpec,
)
from app.services.broadcast_prepare_publisher import BroadcastPreparePublisher
from app.services.email_rendering_service import (
    ConflictingContentError,
    EmailRenderingService,
    MissingFieldError,
    TemplateNotFoundError,
)


class SendBroadcastCommand:
    def __init__(self, db: Session):
        self.db = db
        self.broadcast_repo = BroadcastRepository(db)
        self.suppression_repo = SuppressionRepository(db)
        self.rendering = EmailRenderingService(db)

    def execute(self, req: BroadcastCreateRequest) -> BroadcastBatch:
        content_spec = ContentSpec.from_request(req)

        # Content-level mistakes (missing subject/html, unresolvable
        # template) affect every recipient identically — validate once here
        # so the caller gets an immediate 4xx instead of every recipient
        # silently failing, one by one, deep in the async prepare stage.
        try:
            self.rendering.validate(content_spec)
        except TemplateNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ConflictingContentError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except MissingFieldError as e:
            raise HTTPException(status_code=422, detail=str(e))

        fingerprint = self._fingerprint(content_spec, req.recipients)

        if req.idempotency_key:
            existing = self.broadcast_repo.get_batch_by_idempotency_key(
                req.project_id, req.idempotency_key
            )
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "idempotency_key was already used with a different "
                            "request."
                        ),
                    )
                return existing

        emails = [str(recipient.email) for recipient in req.recipients]
        if req.project_id is None:
            # Global broadcast: no single project's suppression list applies,
            # so a recipient suppressed in ANY project is skipped.
            suppressed_emails = self.suppression_repo.is_suppressed_bulk_any_project(
                emails
            )
        else:
            suppressed_emails = self.suppression_repo.is_suppressed_bulk(
                req.project_id, emails
            )

        batch_id = str(uuid.uuid4())
        queued_count = len(emails) - len(suppressed_emails)
        suppressed_count = len(suppressed_emails)

        batch = self.broadcast_repo.create_batch(
            project_id=req.project_id,
            batch_id=batch_id,
            idempotency_key=req.idempotency_key,
            request_fingerprint=fingerprint,
            content_spec=content_spec.model_dump(mode="json"),
            queued_count=queued_count,
            suppressed_count=suppressed_count,
        )
        self.broadcast_repo.bulk_create_recipients(
            broadcast_batch_id=batch.id,
            recipients=req.recipients,
            suppressed_emails=suppressed_emails,
        )

        # Fast path: dispatch the prepare stage synchronously, after commit.
        BroadcastPreparePublisher(self.db).dispatch_for_batch(batch.id)

        return batch

    @staticmethod
    def _fingerprint(
        content_spec: ContentSpec, recipients: List[BroadcastRecipient]
    ) -> str:
        payload = {
            "content_spec": content_spec.model_dump(mode="json"),
            "recipients": [r.model_dump(mode="json") for r in recipients],
        }
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
