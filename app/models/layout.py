from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.db import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class Layout(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "layouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    html = Column(Text, nullable=False)

    templates = relationship("Template", back_populates="layout")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
