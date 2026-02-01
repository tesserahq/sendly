from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class EmailEventBase(BaseModel):
    """Base email event model containing common email event attributes."""

    event_type: str
    """Event type (e.g., 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'failed'). Required field."""

    event_timestamp: datetime
    """Timestamp when the event occurred. Required field."""

    details: Dict[str, Any]
    """Event details as JSON. Required field."""


class EmailEventCreate(EmailEventBase):
    """Schema for creating a new email event."""

    email_id: UUID
    """Email ID this event belongs to. Required field."""


class EmailEventUpdate(BaseModel):
    """Schema for updating an existing email event. All fields are optional."""

    event_type: Optional[str] = None
    """Updated event type."""

    event_timestamp: Optional[datetime] = None
    """Updated event timestamp."""

    details: Optional[Dict[str, Any]] = None
    """Updated event details."""


class EmailEventInDB(EmailEventBase):
    """Schema representing an email event as stored in the database."""

    id: UUID
    """Unique identifier for the email event in the database."""

    email_id: UUID
    """Email ID this event belongs to."""

    created_at: datetime
    """Timestamp when the email event record was created."""

    updated_at: datetime
    """Timestamp when the email event record was last updated."""

    model_config = {"from_attributes": True}


class EmailEvent(EmailEventInDB):
    """Schema for email event data returned in API responses."""

    pass


class EmailBase(BaseModel):
    """Base email model containing common email attributes."""

    from_email: EmailStr
    """Sender email address. Required field."""

    to_email: EmailStr
    """Recipient email address. Required field."""

    subject: str
    """Email subject. Required field."""

    body: str
    """Email body content. Required field."""

    status: str
    """Email status (e.g., 'pending', 'sent', 'delivered', 'failed'). Required field."""

    provider: str
    """Provider ID used to send the email. Required field."""

    provider_message_id: Optional[str] = None
    """Provider message ID."""

    project_id: Optional[UUID] = None
    """Project ID that owns this email. Optional field."""


class EmailCreate(EmailBase):
    """Schema for creating a new email. Inherits all fields from EmailBase."""

    pass


class EmailUpdate(BaseModel):
    """Schema for updating an existing email. All fields are optional."""

    from_email: Optional[EmailStr] = None
    """Updated sender email address."""

    to_email: Optional[EmailStr] = None
    """Updated recipient email address."""

    subject: Optional[str] = None
    """Updated email subject."""

    body: Optional[str] = None
    """Updated email body content."""

    status: Optional[str] = None
    """Updated email status."""

    sent_at: Optional[datetime] = None
    """Updated sent timestamp."""

    provider_message_id: Optional[str] = None
    """Updated provider message ID."""

    error_message: Optional[str] = None
    """Updated error message."""


class EmailInDB(EmailBase):
    """Schema representing an email as stored in the database. Includes database-specific fields."""

    id: UUID
    """Unique identifier for the email in the database."""

    sent_at: Optional[datetime] = None
    """Timestamp when the email was sent to the provider."""

    error_message: Optional[str] = None
    """Error message if email sending failed."""

    created_at: datetime
    """Timestamp when the email record was created."""

    updated_at: datetime
    """Timestamp when the email record was last updated."""

    model_config = {"from_attributes": True}


class Email(EmailInDB):
    """Schema for email data returned in API responses. Inherits all fields from EmailInDB."""

    pass


class EmailWithEventsResponse(EmailInDB):
    """Schema for email data with associated events response."""

    events: list[EmailEvent] = []
    """List of events associated with this email."""
