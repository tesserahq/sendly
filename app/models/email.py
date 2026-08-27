from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

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
    opened_at = Column(DateTime, nullable=True)  # when the email was first opened
    clicked_at = Column(DateTime, nullable=True)  # when a link was first clicked
    provider = Column(String, nullable=False)
    provider_message_id = Column(String, nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    reply_to = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    batch_id = Column(String, nullable=True, index=True)
    tags = Column(JSONB, nullable=True)
    # "metadata" is reserved on the declarative Base (holds schema MetaData),
    # so the Python attribute is "metadata_" while the DB column stays "metadata".
    metadata_ = Column("metadata", JSONB, nullable=True)

    events = relationship("EmailEvent", back_populates="email")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
