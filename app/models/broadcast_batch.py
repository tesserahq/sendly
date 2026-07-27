from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class BroadcastBatch(Base, TimestampMixin, SoftDeleteMixin):
    """A single POST /broadcasts/send acceptance: shared content spec + accept-time counts."""

    __tablename__ = "broadcast_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    batch_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    request_fingerprint = Column(String, nullable=True)
    content_spec = Column(JSONB, nullable=False)
    queued_count = Column(Integer, nullable=False, default=0)
    suppressed_count = Column(Integer, nullable=False, default=0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
