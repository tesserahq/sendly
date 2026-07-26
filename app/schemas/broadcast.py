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
    """

    project_id: UUID
    from_email: Optional[EmailStr] = None
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
    recipients: List[BroadcastRecipient]


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
