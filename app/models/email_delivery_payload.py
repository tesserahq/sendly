from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

import uuid

from app.db import Base
from app.models.mixins import TimestampMixin


class EmailDeliveryPayload(Base, TimestampMixin):
    """Immutable, fully-resolved delivery payload for one Email.

    Written once by the prepare stage; the send stage reads it verbatim and
    never re-fetches a template or depends on request-only recipient data.
    """

    __tablename__ = "email_delivery_payloads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False, unique=True
    )
    from_email = Column(String, nullable=False)
    reply_to = Column(String, nullable=True)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    html = Column(String, nullable=True)
    text = Column(String, nullable=True)
    attachments = Column(JSONB, nullable=False, default=list)
    custom_headers = Column(JSONB, nullable=False, default=dict)
    message_stream = Column(String, nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
