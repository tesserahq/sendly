from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, String, Boolean, DateTime, Index, text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base


class Tenant(Base, TimestampMixin, SoftDeleteMixin):
    """Provider model for the application.
    This model represents a provider in the system.
    """

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False)
    provider_api_key = Column(String, nullable=False)
    provider_metadata = Column(JSONB, nullable=False)

    provider = relationship("Provider", back_populates="tenants")
    emails = relationship("Email", back_populates="tenant")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
