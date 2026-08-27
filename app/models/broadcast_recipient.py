from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
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
    __table_args__ = (
        # Non-null caller references must be unique within one batch;
        # Postgres treats NULLs as distinct, so recipients without a
        # reference are unaffected. See docs/prds/0004-*.md.
        UniqueConstraint(
            "broadcast_batch_id",
            "client_reference_id",
            name="uq_broadcast_recipients_batch_reference",
        ),
    )

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
    # Caller-supplied correlation identifier; unique within one batch when
    # provided (see uq_broadcast_recipients_batch_reference above).
    client_reference_id = Column(UUID(as_uuid=True), nullable=True)
    # Nullable, unique: the one Email this recipient produced, populated by
    # the prepare stage. Suppressed recipients and rendering failures never
    # get one. Also serves as the one-email-per-recipient invariant required
    # by the broadcast pipeline reliability design.
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=True, unique=True
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
