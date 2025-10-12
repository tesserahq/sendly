# sendly/providers/base.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


# ---------------------------
# Pydantic I/O Schemas
# ---------------------------


class Attachment(BaseModel):
    filename: str
    content_bytes_b64: str  # base64-encoded content
    mime_type: str = "application/octet-stream"


class EmailPersonalization(BaseModel):
    to: List[EmailStr]
    cc: List[EmailStr] = []
    bcc: List[EmailStr] = []


class EmailSendRequest(BaseModel):
    tenant_id: str
    from_email: EmailStr
    subject: str
    html: Optional[str] = None
    text: Optional[str] = None
    attachments: List[Attachment] = []
    personalization: EmailPersonalization
    template_id: Optional[str] = None
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    priority: Optional[int] = None
    # Optional idempotency key to dedupe client retries
    idempotency_key: Optional[str] = None


class EmailSendResult(BaseModel):
    ok: bool
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    # Anything provider-specific
    provider_meta: Dict[str, Any] = Field(default_factory=dict)


# Normalized webhook event
class EmailEvent(BaseModel):
    tenant_id: str
    provider_name: str
    provider_message_id: str
    type: str  # sent|delivered|opened|clicked|bounced|complained|dropped|deferred|spam|unsubscribed
    occurred_at: datetime
    raw_payload: Dict[str, Any]
