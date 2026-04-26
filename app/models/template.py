from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.db import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class Template(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    html = Column(Text, nullable=False)
    from_email = Column(String, nullable=True)
    reply_to = Column(String, nullable=True)
    layout_id = Column(UUID(as_uuid=True), ForeignKey("layouts.id"), nullable=True)

    layout = relationship("Layout", back_populates="templates")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
