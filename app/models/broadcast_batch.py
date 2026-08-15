from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class BroadcastBatch(Base, TimestampMixin, SoftDeleteMixin):
    """A single POST /broadcasts/send acceptance: shared content spec + accept-time counts."""

    __tablename__ = "broadcast_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    batch_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    request_fingerprint = Column(String, nullable=True)
    content_spec = Column(JSONB, nullable=False)
    queued_count = Column(Integer, nullable=False, default=0)
    suppressed_count = Column(Integer, nullable=False, default=0)
    # Denormalized, updated at the prepare/send write points instead of
    # computed live — see BroadcastRepository.increment_prepared_count and
    # .maybe_mark_finished. Pre-migration rows default to 0/False and are
    # not backfilled.
    prepared_count = Column(Integer, nullable=False, default=0)
    finished = Column(Boolean, nullable=False, default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
