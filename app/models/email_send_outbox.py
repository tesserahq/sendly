from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin


class EmailSendOutbox(Base, TimestampMixin):
    """One pending-send marker per Email, consumed (chunked) by the send stage."""

    __tablename__ = "email_send_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False, unique=True
    )
    processed_at = Column(DateTime, nullable=True, index=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
