from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient


class BroadcastRepository:
    """Data access for broadcast_batches and broadcast_recipients."""

    def __init__(self, db: Session):
        self.db = db

    # ==================== BroadcastBatch ====================

    def get_batch_by_id(self, batch_pk: UUID) -> Optional[BroadcastBatch]:
        return (
            self.db.query(BroadcastBatch).filter(BroadcastBatch.id == batch_pk).first()
        )

    def get_batch_by_idempotency_key(
        self, project_id: UUID, idempotency_key: str
    ) -> Optional[BroadcastBatch]:
        return (
            self.db.query(BroadcastBatch)
            .filter(
                BroadcastBatch.project_id == project_id,
                BroadcastBatch.idempotency_key == idempotency_key,
            )
            .first()
        )

    def get_batch_by_batch_id(self, batch_id: str) -> Optional[BroadcastBatch]:
        """batch_id is server-generated (a UUID) and globally unique — no
        project_id scoping needed, unlike idempotency_key (caller-chosen,
        legitimately reused across different projects/callers)."""
        return (
            self.db.query(BroadcastBatch)
            .filter(BroadcastBatch.batch_id == batch_id)
            .first()
        )

    def create_batch(
        self,
        *,
        project_id: UUID,
        batch_id: str,
        idempotency_key: Optional[str],
        request_fingerprint: str,
        content_spec: Dict[str, Any],
        queued_count: int,
        suppressed_count: int,
    ) -> BroadcastBatch:
        batch = BroadcastBatch(
            project_id=project_id,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            content_spec=content_spec,
            queued_count=queued_count,
            suppressed_count=suppressed_count,
        )
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    # ==================== BroadcastRecipient ====================

    def bulk_create_recipients(
        self,
        *,
        broadcast_batch_id: UUID,
        recipients: Sequence[Any],
        suppressed_emails: Set[str],
    ) -> None:
        rows = [
            BroadcastRecipient(
                broadcast_batch_id=broadcast_batch_id,
                email=str(recipient.email),
                first_name=recipient.first_name,
                last_name=recipient.last_name,
                attributes=recipient.attributes,
                suppressed=str(recipient.email) in suppressed_emails,
                prepared=False,
            )
            for recipient in recipients
        ]
        self.db.add_all(rows)
        self.db.commit()

    def get_unprepared_recipients(
        self, broadcast_batch_id: UUID, limit: Optional[int] = None
    ) -> List[BroadcastRecipient]:
        """Unprepared, non-suppressed recipients for one batch (what prepare dispatches)."""
        query = self.db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_batch_id == broadcast_batch_id,
            BroadcastRecipient.prepared.is_(False),
            BroadcastRecipient.suppressed.is_(False),
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_recipients_by_ids(self, ids: Sequence[UUID]) -> List[BroadcastRecipient]:
        return (
            self.db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id.in_(ids))
            .all()
        )

    def mark_recipients_prepared(self, ids: Sequence[UUID]) -> None:
        if not ids:
            return
        self.db.query(BroadcastRecipient).filter(BroadcastRecipient.id.in_(ids)).update(
            {"prepared": True}, synchronize_session=False
        )
        self.db.commit()

    def count_prepared(self, broadcast_batch_id: UUID) -> int:
        return (
            self.db.query(BroadcastRecipient)
            .filter(
                BroadcastRecipient.broadcast_batch_id == broadcast_batch_id,
                BroadcastRecipient.prepared.is_(True),
            )
            .count()
        )

    def get_stale_unprepared_batch_ids(self, older_than: datetime) -> List[UUID]:
        """Batch PKs with unprepared, non-suppressed recipients past the grace period."""
        rows = (
            self.db.query(BroadcastRecipient.broadcast_batch_id)
            .filter(
                BroadcastRecipient.prepared.is_(False),
                BroadcastRecipient.suppressed.is_(False),
                BroadcastRecipient.created_at < older_than,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows]
