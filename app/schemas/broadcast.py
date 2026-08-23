from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.providers.base import Attachment


class BroadcastRecipient(BaseModel):
    """One recipient in a broadcast send: email required, everything else optional."""

    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BroadcastCreateRequest(BaseModel):
    """Request body for POST /broadcasts/send.

    Reuses the same content options /emails already supports; batch_id, cc,
    bcc, and priority are intentionally absent — Sendly generates batch_id
    and cc/bcc have no coherent per-recipient meaning for a fan-out send.

    project_id is omitted for a global (org-wide, not tenant-scoped)
    broadcast — requires a "*"-domain grant in Custos; see infer_project
    in app/routers/broadcast.py.
    """

    project_id: Optional[UUID] = None
    from_email: Optional[EmailStr] = None
    reply_to: Optional[EmailStr] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    attachments: List[Attachment] = Field(default_factory=list)
    template_id: Optional[UUID] = None
    template_alias: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    recipients: List[BroadcastRecipient] = Field(min_length=1)


class ContentSpec(BaseModel):
    """The shared, not-yet-rendered content options for a broadcast batch.

    Persisted as JSONB on BroadcastBatch.content_spec and re-validated by the
    prepare stage (`ContentSpec.model_validate(batch.content_spec)`) — a
    typed boundary instead of passing a raw dict around and reading it back
    with `.get("some_key")` string lookups scattered across the codebase.
    """

    html: Optional[str] = None
    text: Optional[str] = None
    template_id: Optional[str] = None
    template_alias: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    subject: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    attachments: List[Attachment] = Field(default_factory=list)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_request(cls, req: "BroadcastCreateRequest") -> "ContentSpec":
        return cls(
            html=req.html,
            text=req.text,
            template_id=str(req.template_id) if req.template_id else None,
            template_alias=req.template_alias,
            template_variables=req.template_variables,
            subject=req.subject,
            from_email=req.from_email,
            reply_to=req.reply_to,
            custom_headers=req.custom_headers,
            attachments=req.attachments,
            tags=req.tags,
            metadata=req.metadata,
        )


class BroadcastSendResponse(BaseModel):
    """Immediate response to POST /broadcasts/send."""

    batch_id: str
    queued_count: int
    suppressed_count: int


class BroadcastStatusResponse(BaseModel):
    """Response for GET /broadcasts/{batch_id}."""

    batch_id: str
    queued_count: int
    suppressed_count: int
    prepared_count: int
    finished: bool
    """True once the send stage has been attempted for every queued
    recipient (prepared_count == queued_count and no outbox entries for
    this batch are still pending). Does not track post-send webhook
    updates (opened/clicked/bounced, etc.) — those keep updating individual
    Email rows independently, same as single-send, indefinitely."""
    delivered_count: int
    bounced_count: int
    complained_count: int
    """Delivery-outcome rollups, denormalized from webhook ingestion — see
    BroadcastRepository.increment_delivery_counter. Each counts emails that
    have ever reached that status; unlike prepared_count/finished, these
    keep updating indefinitely after the batch is finished."""


class BroadcastBatchSummary(BaseModel):
    """One row of GET /broadcasts.

    prepared_count/finished are denormalized columns on BroadcastBatch,
    updated at the prepare/send write points rather than computed live —
    safe to include per row without an N+1 query pattern across a page.
    """

    model_config = {"from_attributes": True}

    batch_id: str
    project_id: Optional[UUID]
    queued_count: int
    suppressed_count: int
    prepared_count: int
    finished: bool
    delivered_count: int
    bounced_count: int
    complained_count: int
    created_at: datetime
