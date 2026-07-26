"""Periodic Celery-beat crash-recovery backstops for the prepare/send stages.

Not the normal dispatch path — both stages dispatch their own chunks
synchronously right after commit. These sweeps only catch rows/entries left
behind by a crash between commit and dispatch.
"""

from __future__ import annotations

from app.core.celery_app import celery_app
from app.db import SessionLocal
from app.services.broadcast_outbox_publisher import BroadcastOutboxPublisher
from app.services.broadcast_prepare_publisher import BroadcastPreparePublisher


@celery_app.task(name="app.tasks.prepare_recovery_sweep")
def prepare_recovery_sweep_task() -> int:
    db = SessionLocal()
    try:
        return BroadcastPreparePublisher(db).run_recovery_sweep()
    finally:
        db.close()


@celery_app.task(name="app.tasks.outbox_recovery_sweep")
def outbox_recovery_sweep_task() -> int:
    db = SessionLocal()
    try:
        return BroadcastOutboxPublisher(db).run_recovery_sweep()
    finally:
        db.close()
