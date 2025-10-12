from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from slugify import slugify
import uuid

from app.db import Base


class Provider(Base, TimestampMixin, SoftDeleteMixin):
    """Provider model for the application.
    This model represents a provider in the system.
    """

    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)

    tenants = relationship("Tenant", back_populates="provider")
    emails = relationship("Email", back_populates="provider")

    def slug(self) -> str:
        return slugify(self.name)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
