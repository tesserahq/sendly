"""Unit tests for BroadcastPreparePublisher: chunk grouping and both triggers.
No Celery, no HTTP — the repository and the task's .delay are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.broadcast_prepare_publisher import BroadcastPreparePublisher


def _make_recipient(recipient_id=None):
    recipient = MagicMock()
    recipient.id = recipient_id or uuid4()
    return recipient


class TestDispatchForBatch:
    def test_dispatches_one_task_per_chunk(self):
        batch_id = uuid4()
        recipients = [_make_recipient() for _ in range(5)]

        publisher = BroadcastPreparePublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_unprepared_recipients.return_value = recipients

        with (
            patch(
                "app.services.broadcast_prepare_publisher.get_settings"
            ) as mock_settings,
            patch(
                "app.tasks.prepare_broadcast_chunk_task.prepare_broadcast_chunk_task"
            ) as mock_task,
        ):
            mock_settings.return_value.broadcast_chunk_size = 2
            dispatched = publisher.dispatch_for_batch(batch_id)

        assert dispatched == 5
        assert mock_task.delay.call_count == 3  # chunks of 2, 2, 1
        first_call_ids = mock_task.delay.call_args_list[0][0][1]
        assert len(first_call_ids) == 2

    def test_only_dispatches_unprepared_non_suppressed_recipients(self):
        batch_id = uuid4()
        publisher = BroadcastPreparePublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_unprepared_recipients.return_value = []

        with patch(
            "app.tasks.prepare_broadcast_chunk_task.prepare_broadcast_chunk_task"
        ) as mock_task:
            dispatched = publisher.dispatch_for_batch(batch_id)

        publisher.repo.get_unprepared_recipients.assert_called_once_with(batch_id)
        assert dispatched == 0
        mock_task.delay.assert_not_called()


class TestRunRecoverySweep:
    def test_dispatches_for_each_stale_batch(self):
        stale_batch_ids = [uuid4(), uuid4()]
        publisher = BroadcastPreparePublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_stale_unprepared_batch_ids.return_value = stale_batch_ids
        publisher.repo.get_unprepared_recipients.return_value = [_make_recipient()]

        with patch(
            "app.tasks.prepare_broadcast_chunk_task.prepare_broadcast_chunk_task"
        ) as mock_task:
            dispatched = publisher.run_recovery_sweep()

        assert dispatched == 2
        assert mock_task.delay.call_count == 2

    def test_does_not_redispatch_already_prepared_rows(self):
        """get_stale_unprepared_batch_ids/get_unprepared_recipients already
        filter to prepared=False rows only — nothing extra to claim here."""
        publisher = BroadcastPreparePublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_stale_unprepared_batch_ids.return_value = []

        dispatched = publisher.run_recovery_sweep()

        assert dispatched == 0
        publisher.repo.get_unprepared_recipients.assert_not_called()
