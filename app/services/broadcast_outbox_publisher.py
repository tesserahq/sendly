"""Dispatches the send stage: chunked Celery tasks that call Postmark's Bulk
API for a set of pending email_send_outbox entries.

Same two-trigger shape as the prepare publisher, one stage later:
  1. Fast path: prepare_broadcast_chunk_task calls dispatch() directly,
     synchronously, right after its own transaction commits.
  2. Recovery path: a periodic Celery-beat sweep (run_recovery_sweep) over
     entries pending past a grace period, across all batches.

A chunk boundary never spans more than one broadcast batch (mirrored here by
grouping recovery-sweep entries by Email.batch_id before chunking), though it
may be smaller than broadcast_chunk_size on the tail of a batch or a prepare
chunk.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories.email_send_outbox_repository import EmailSendOutboxRepository
from app.utils.chunking import chunked

GRACE_PERIOD = timedelta(minutes=5)


class BroadcastOutboxPublisher:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EmailSendOutboxRepository(db)

    def dispatch(self, email_ids: List[UUID]) -> int:
        from app.tasks.send_broadcast_chunk_task import send_broadcast_chunk_task

        chunk_size = get_settings().broadcast_chunk_size
        dispatched = 0
        for chunk in chunked(email_ids, chunk_size):
            send_broadcast_chunk_task.delay([str(email_id) for email_id in chunk])
            dispatched += len(chunk)
        return dispatched

    def run_recovery_sweep(self) -> int:
        cutoff = datetime.now(timezone.utc) - GRACE_PERIOD
        stale_entries = self.repo.get_pending_older_than_with_batch(cutoff)

        by_batch: dict = defaultdict(list)
        for email_id, batch_id in stale_entries:
            by_batch[batch_id].append(email_id)

        dispatched = 0
        for email_ids in by_batch.values():
            dispatched += self.dispatch(email_ids)
        return dispatched
