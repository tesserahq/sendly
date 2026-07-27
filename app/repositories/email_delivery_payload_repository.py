from typing import Any, List, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.email_delivery_payload import EmailDeliveryPayload


class EmailDeliveryPayloadRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_payload(self, **kwargs: Any) -> EmailDeliveryPayload:
        payload = EmailDeliveryPayload(**kwargs)
        self.db.add(payload)
        self.db.commit()
        self.db.refresh(payload)
        return payload

    def get_by_email_id(self, email_id: UUID) -> Optional[EmailDeliveryPayload]:
        return (
            self.db.query(EmailDeliveryPayload)
            .filter(EmailDeliveryPayload.email_id == email_id)
            .first()
        )

    def get_by_email_ids(self, email_ids: Sequence[UUID]) -> List[EmailDeliveryPayload]:
        return (
            self.db.query(EmailDeliveryPayload)
            .filter(EmailDeliveryPayload.email_id.in_(email_ids))
            .all()
        )
