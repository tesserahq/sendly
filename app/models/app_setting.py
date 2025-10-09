from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db import Base


class AppSetting(Base, TimestampMixin, SoftDeleteMixin):
    """AppSettings model for the application."""

    __tablename__ = "app_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(50), nullable=False)
    value = Column(String, nullable=False)
