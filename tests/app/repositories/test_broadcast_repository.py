"""Tests for the denormalized prepared_count/finished/delivery-outcome
write paths on BroadcastRepository."""

from __future__ import annotations

from uuid import uuid4

from app.constants.email import EmailStatus
from app.models.broadcast_batch import BroadcastBatch
from app.repositories.broadcast_repository import BroadcastRepository


def _make_batch(db, **overrides):
    defaults = dict(
        project_id=uuid4(),
        batch_id=str(uuid4()),
        idempotency_key=None,
        request_fingerprint="fp",
        content_spec={},
        queued_count=2,
        suppressed_count=0,
    )
    defaults.update(overrides)
    batch = BroadcastBatch(**defaults)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


class TestIncrementPreparedCount:
    def test_increments_by_given_amount(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_prepared_count(batch.id, 1)
        repo.increment_prepared_count(batch.id, 1)

        db.refresh(batch)
        assert batch.prepared_count == 2

    def test_zero_or_negative_is_a_no_op(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_prepared_count(batch.id, 0)
        repo.increment_prepared_count(batch.id, -1)

        db.refresh(batch)
        assert batch.prepared_count == 0


class TestMaybeMarkFinished:
    def test_marks_finished_when_prepared_matches_queued_and_nothing_pending(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db, queued_count=2)
        repo.increment_prepared_count(batch.id, 2)

        result = repo.maybe_mark_finished(batch.id, pending_send_count=0)

        assert result is True
        db.refresh(batch)
        assert batch.finished is True

    def test_does_not_mark_finished_while_prepare_incomplete(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db, queued_count=2)
        repo.increment_prepared_count(batch.id, 1)

        result = repo.maybe_mark_finished(batch.id, pending_send_count=0)

        assert result is False
        db.refresh(batch)
        assert batch.finished is False

    def test_does_not_mark_finished_while_send_pending(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db, queued_count=2)
        repo.increment_prepared_count(batch.id, 2)

        result = repo.maybe_mark_finished(batch.id, pending_send_count=1)

        assert result is False
        db.refresh(batch)
        assert batch.finished is False

    def test_is_idempotent_once_already_finished(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db, queued_count=1)
        repo.increment_prepared_count(batch.id, 1)
        assert repo.maybe_mark_finished(batch.id, pending_send_count=0) is True

        result = repo.maybe_mark_finished(batch.id, pending_send_count=0)

        assert result is False


class TestIncrementDeliveryCounter:
    def test_increments_delivered_count_for_delivered_status(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_delivery_counter(batch.id, EmailStatus.DELIVERED)
        repo.increment_delivery_counter(batch.id, EmailStatus.DELIVERED)

        db.refresh(batch)
        assert batch.delivered_count == 2

    def test_is_a_no_op_for_untracked_statuses(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_delivery_counter(batch.id, EmailStatus.SENT)

        db.refresh(batch)
        assert batch.delivered_count == 0

    def test_is_a_no_op_for_engagement_statuses(self, db):
        """opened/clicked are no longer driven by increment_delivery_counter
        — see TestIncrementEngagementCounter — since they're first-occurrence
        outcomes rather than plain status transitions."""
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_delivery_counter(batch.id, EmailStatus.OPENED)
        repo.increment_delivery_counter(batch.id, EmailStatus.CLICKED)

        db.refresh(batch)
        assert batch.opened_count == 0
        assert batch.clicked_count == 0


class TestIncrementEngagementCounter:
    def test_increments_opened_count(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_engagement_counter(batch.id, "opened")
        repo.increment_engagement_counter(batch.id, "opened")

        db.refresh(batch)
        assert batch.opened_count == 2
        assert batch.clicked_count == 0

    def test_increments_clicked_count(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_engagement_counter(batch.id, "clicked")

        db.refresh(batch)
        assert batch.clicked_count == 1
        assert batch.opened_count == 0

    def test_is_a_no_op_for_untracked_engagement_kinds(self, db):
        repo = BroadcastRepository(db)
        batch = _make_batch(db)

        repo.increment_engagement_counter(batch.id, "bounced")

        db.refresh(batch)
        assert batch.opened_count == 0
        assert batch.clicked_count == 0
