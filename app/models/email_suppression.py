from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class EmailSuppression(Base, TimestampMixin, SoftDeleteMixin):
    """A project-scoped recipient that must be skipped on future broadcast sends."""

    __tablename__ = "email_suppressions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    email = Column(String, nullable=False)
    unsubscribed_at = Column(DateTime, nullable=False)
    source = Column(String, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
