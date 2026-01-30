from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, ForeignKey, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

import uuid

from app.db import Base


class Email(Base, TimestampMixin, SoftDeleteMixin):
    """Email model for the application.
    This model represents a provider in the system.
    """

    __tablename__ = "emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_email = Column(String, nullable=False)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(String, nullable=False)
    status = Column(String, nullable=False)
    sent_at = Column(DateTime, nullable=True)  # when the email was sent to the provider
    provider = Column(String, nullable=False)
    provider_message_id = Column(String, nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    error_message = Column(String, nullable=True)

    events = relationship("EmailEvent", back_populates="email")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
