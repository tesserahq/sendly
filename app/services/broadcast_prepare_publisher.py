"""Dispatches the prepare stage: chunked Celery tasks that render content and
create Email/payload/outbox rows for a batch's unprepared recipients.

Two triggers, same shape the outbox publisher uses one stage later:
  1. Fast path: SendBroadcastCommand calls dispatch_for_batch() directly,
     synchronously, right after its transaction commits.
  2. Recovery path: a periodic Celery-beat sweep (run_recovery_sweep) over
     unprepared rows older than a grace period, across all batches — a
     crash-recovery backstop, not the normal dispatch path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories.broadcast_repository import BroadcastRepository
from app.utils.chunking import chunked

GRACE_PERIOD = timedelta(minutes=5)


class BroadcastPreparePublisher:
    def __init__(self, db: Session):
        self.db = db
        self.repo = BroadcastRepository(db)

    def dispatch_for_batch(self, broadcast_batch_id: UUID) -> int:
        from app.tasks.prepare_broadcast_chunk_task import prepare_broadcast_chunk_task

        recipients = self.repo.get_unprepared_recipients(broadcast_batch_id)
        chunk_size = get_settings().broadcast_chunk_size

        dispatched = 0
        for chunk in chunked(recipients, chunk_size):
            ids: List[str] = [str(recipient.id) for recipient in chunk]
            prepare_broadcast_chunk_task.delay(str(broadcast_batch_id), ids)
            dispatched += len(ids)
        return dispatched

    def run_recovery_sweep(self) -> int:
        cutoff = datetime.now(timezone.utc) - GRACE_PERIOD
        stale_batch_ids = self.repo.get_stale_unprepared_batch_ids(cutoff)

        dispatched = 0
        for broadcast_batch_id in stale_batch_ids:
            dispatched += self.dispatch_for_batch(broadcast_batch_id)
        return dispatched
