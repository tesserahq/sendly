from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.email_send_outbox import EmailSendOutbox


class EmailSendOutboxRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_entry(self, email_id: UUID) -> EmailSendOutbox:
        entry = EmailSendOutbox(email_id=email_id)
        self.db.add(entry)
        self.db.flush()
        self.db.refresh(entry)
        return entry

    def get_pending_older_than_with_batch(
        self, cutoff: datetime
    ) -> list[tuple[UUID, str]]:
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

    def count_pending_for_batch(self, batch_id: str) -> int:
        """Outbox rows still missing processed_at for one broadcast batch —
        used to tell whether the send stage has finished for that batch."""
        return (
            self.db.query(EmailSendOutbox)
            .join(Email, Email.id == EmailSendOutbox.email_id)
            .filter(
                EmailSendOutbox.processed_at.is_(None),
                Email.batch_id == batch_id,
            )
            .count()
        )

    def mark_processed(self, email_ids: Sequence[UUID]) -> None:
        if not email_ids:
            return
        statement = (
            update(EmailSendOutbox)
            .where(EmailSendOutbox.email_id.in_(email_ids))
            .values(processed_at=datetime.now(UTC))
        )
        self.db.execute(statement, execution_options={"synchronize_session": "fetch"})
