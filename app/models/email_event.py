from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, ForeignKey, String, Boolean, DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base


class EmailEvent(Base, TimestampMixin, SoftDeleteMixin):
    """EmailEvent model for the application.
    This model represents an email event in the system.
    """

    __tablename__ = "email_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False)
    event_type = Column(String, nullable=False)
    event_timestamp = Column(DateTime, nullable=False)
    details = Column(JSONB, nullable=False)

    email = relationship("Email", back_populates="events")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
