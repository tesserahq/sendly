from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin


class BroadcastRecipient(Base, TimestampMixin):
    """Raw, unrendered per-recipient data submitted with a broadcast send.

    Consumed by the prepare stage, which renders content and creates the
    corresponding Email/delivery-payload/outbox rows.
    """

    __tablename__ = "broadcast_recipients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broadcast_batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("broadcast_batches.id"),
        nullable=False,
        index=True,
    )
    email = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    attributes = Column(JSONB, nullable=False, default=dict)
    suppressed = Column(Boolean, nullable=False, default=False)
    prepared = Column(Boolean, nullable=False, default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
