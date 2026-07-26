from datetime import datetime, timezone
from typing import List, Sequence, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.email_send_outbox import EmailSendOutbox


class EmailSendOutboxRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_entry(self, email_id: UUID) -> EmailSendOutbox:
        entry = EmailSendOutbox(email_id=email_id)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_pending_older_than_with_batch(
        self, cutoff: datetime
    ) -> List[Tuple[UUID, str]]:
        """(email_id, Email.batch_id) pairs for the periodic recovery sweep,
        so recovery-sweep chunks still never span more than one broadcast batch."""
        return (
            self.db.query(EmailSendOutbox.email_id, Email.batch_id)
            .join(Email, Email.id == EmailSendOutbox.email_id)
            .filter(
                EmailSendOutbox.processed_at.is_(None),
                EmailSendOutbox.created_at < cutoff,
            )
            .all()
        )

    def mark_processed(self, email_ids: Sequence[UUID]) -> None:
        if not email_ids:
            return
        self.db.query(EmailSendOutbox).filter(
            EmailSendOutbox.email_id.in_(email_ids)
        ).update(
            {"processed_at": datetime.now(timezone.utc)}, synchronize_session=False
        )
        self.db.commit()
