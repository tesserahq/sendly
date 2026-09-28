from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.email import EmailStatus
from app.models.broadcast_batch import BroadcastBatch
from app.models.broadcast_recipient import BroadcastRecipient
from app.repositories.base_repository import Repository


class BroadcastRepository(Repository):
    """Data access for broadcast_batches and broadcast_recipients."""

    def __init__(self, db: Session):
        super().__init__(db)

    # ==================== BroadcastBatch ====================

    def get_batch_by_id(self, batch_pk: UUID) -> BroadcastBatch | None:
        return (
            self.db.query(BroadcastBatch).filter(BroadcastBatch.id == batch_pk).first()
        )

    def get_batch_by_idempotency_key(
        self, project_id: UUID | None, idempotency_key: str
    ) -> BroadcastBatch | None:
        # project_id = NULL never matches in SQL, so a global (no
        # project_id) broadcast needs an explicit IS NULL branch here or
        # idempotency replay would silently create a duplicate batch every
        # time instead of returning the existing one.
        project_filter = (
            BroadcastBatch.project_id.is_(None)
            if project_id is None
            else BroadcastBatch.project_id == project_id
        )
        return (
            self.db.query(BroadcastBatch)
            .filter(
                project_filter,
                BroadcastBatch.idempotency_key == idempotency_key,
            )
            .first()
        )

    def get_batches_query(self, project_id: UUID | None = None):
        """Query for broadcast batches, newest first, for use with
        fastapi-pagination's paginate()."""
        query = self.db.query(BroadcastBatch)
        if project_id is not None:
            query = query.filter(BroadcastBatch.project_id == project_id)
        return query.order_by(BroadcastBatch.created_at.desc())

    def get_batch_by_batch_id(self, batch_id: str) -> BroadcastBatch | None:
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
        project_id: UUID | None,
        batch_id: str,
        idempotency_key: str | None,
        request_fingerprint: str,
        content_spec: dict[str, Any],
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
        self.db.flush()
        self.db.refresh(batch)
        return batch

    # ==================== BroadcastRecipient ====================

    def bulk_create_recipients(
        self,
        *,
        broadcast_batch_id: UUID,
        recipients: Sequence[Any],
        suppressed_emails: set[str],
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
                client_reference_id=recipient.client_reference_id,
            )
            for recipient in recipients
        ]
        self.db.add_all(rows)
        self.db.flush()

    def link_recipient_to_email(self, recipient_id: UUID, email_id: UUID) -> None:
        """Populate the nullable, unique recipient -> email relationship.
        Called by the prepare stage right after it creates the Email for a
        successfully-rendered recipient; suppressed/failed recipients never
        get this call."""
        statement = (
            update(BroadcastRecipient)
            .where(BroadcastRecipient.id == recipient_id)
            .values(email_id=email_id)
        )
        self._execute_mutation(statement)

    def get_unprepared_recipients(
        self, broadcast_batch_id: UUID, limit: int | None = None
    ) -> list[BroadcastRecipient]:
        """Unprepared, non-suppressed recipients for one batch (what prepare dispatches)."""
        query = self.db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_batch_id == broadcast_batch_id,
            BroadcastRecipient.prepared.is_(False),
            BroadcastRecipient.suppressed.is_(False),
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_recipients_by_ids(self, ids: Sequence[UUID]) -> list[BroadcastRecipient]:
        return (
            self.db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.id.in_(ids))
            .all()
        )

    def mark_recipients_prepared(self, ids: Sequence[UUID]) -> None:
        if not ids:
            return
        statement = (
            update(BroadcastRecipient)
            .where(BroadcastRecipient.id.in_(ids))
            .values(prepared=True)
        )
        self._execute_mutation(statement)

    def count_prepared(self, broadcast_batch_id: UUID) -> int:
        return (
            self.db.query(BroadcastRecipient)
            .filter(
                BroadcastRecipient.broadcast_batch_id == broadcast_batch_id,
                BroadcastRecipient.prepared.is_(True),
            )
            .count()
        )

    def increment_prepared_count(self, batch_pk: UUID, by: int) -> int | None:
        """Atomic SQL increment, not read-modify-write — prepare chunks for
        the same batch can run concurrently across Celery workers."""
        if by <= 0:
            return None
        statement = (
            update(BroadcastBatch)
            .where(BroadcastBatch.id == batch_pk)
            .values(prepared_count=BroadcastBatch.prepared_count + by)
            .returning(BroadcastBatch.prepared_count)
        )
        return self._scalar_mutation(statement)

    def maybe_mark_finished(self, batch_pk: UUID, pending_send_count: int) -> bool:
        """Recompute the same finished condition GET /broadcasts/{batch_id}
        used to compute live (prepared_count == queued_count and no
        outbox entries still pending for this batch), and persist it once
        it holds. Idempotent — safe to call from multiple write points
        (prepare and send stages) without double-marking."""
        if pending_send_count != 0:
            return False
        statement = (
            update(BroadcastBatch)
            .where(
                BroadcastBatch.id == batch_pk,
                BroadcastBatch.finished.is_(False),
                BroadcastBatch.prepared_count == BroadcastBatch.queued_count,
            )
            .values(finished=True)
            .returning(BroadcastBatch.id)
        )
        return self._scalar_mutation(statement) is not None

    # Maps the Email.status values that get a denormalized rollup counter to
    # their BroadcastBatch column. Each status is reachable at most once per
    # email, so a plain atomic increment can't double-count as long as the
    # caller only increments on an actual status transition (see
    # EmailLifecycleService.record_webhook_event's return value). opened/
    # clicked are NOT status-driven — see increment_engagement_counter.
    _DELIVERY_COUNTER_COLUMNS = {
        EmailStatus.DELIVERED: BroadcastBatch.delivered_count,
        EmailStatus.BOUNCED: BroadcastBatch.bounced_count,
        EmailStatus.COMPLAINED: BroadcastBatch.complained_count,
    }

    def increment_delivery_counter(self, batch_pk: UUID, status: str) -> None:
        """Atomic SQL increment of the rollup column for `status`, if one
        exists. No-op for statuses without a tracked counter."""
        self._increment_counter(batch_pk, self._DELIVERY_COUNTER_COLUMNS.get(status))

    # Maps a first-occurrence engagement kind (see
    # EmailLifecycleService.WebhookOutcome.first_opened/first_clicked) to its
    # BroadcastBatch column. Driven by the atomic first-occurrence outcome,
    # not by Email.status, so an out-of-order click-before-open webhook
    # sequence still counts both exactly once each.
    _ENGAGEMENT_COUNTER_COLUMNS = {
        "opened": BroadcastBatch.opened_count,
        "clicked": BroadcastBatch.clicked_count,
    }

    def increment_engagement_counter(self, batch_pk: UUID, engagement: str) -> None:
        """Atomic SQL increment of the rollup column for `engagement`
        ("opened" or "clicked"), if one exists."""
        self._increment_counter(
            batch_pk, self._ENGAGEMENT_COUNTER_COLUMNS.get(engagement)
        )

    def _increment_counter(self, batch_pk: UUID, column) -> None:
        """Shared atomic SQL increment used by both counter families above.
        No-op when `column` is None (an untracked status/engagement kind)."""
        if column is None:
            return
        statement = (
            update(BroadcastBatch)
            .where(BroadcastBatch.id == batch_pk)
            .values({column.key: column + 1})
        )
        self._execute_mutation(statement)

    def get_stale_unprepared_batch_ids(self, older_than: datetime) -> list[UUID]:
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
