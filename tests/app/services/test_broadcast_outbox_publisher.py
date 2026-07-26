"""Unit tests for BroadcastOutboxPublisher: chunk grouping (respecting
broadcast_chunk_size, tail chunk smaller not dropped/merged) and both
triggers. No Celery, no HTTP.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.broadcast_outbox_publisher import BroadcastOutboxPublisher


class TestDispatch:
    def test_dispatches_one_task_per_chunk_respecting_chunk_size(self):
        email_ids = [uuid4() for _ in range(5)]
        publisher = BroadcastOutboxPublisher(db=MagicMock())

        with (
            patch(
                "app.services.broadcast_outbox_publisher.get_settings"
            ) as mock_settings,
            patch(
                "app.tasks.send_broadcast_chunk_task.send_broadcast_chunk_task"
            ) as mock_task,
        ):
            mock_settings.return_value.broadcast_chunk_size = 2
            dispatched = publisher.dispatch(email_ids)

        assert dispatched == 5
        call_sizes = [len(call[0][0]) for call in mock_task.delay.call_args_list]
        assert call_sizes == [2, 2, 1]  # tail chunk kept smaller, not dropped/merged

    def test_empty_list_dispatches_nothing(self):
        publisher = BroadcastOutboxPublisher(db=MagicMock())
        with patch(
            "app.tasks.send_broadcast_chunk_task.send_broadcast_chunk_task"
        ) as mock_task:
            dispatched = publisher.dispatch([])
        assert dispatched == 0
        mock_task.delay.assert_not_called()


class TestRunRecoverySweep:
    def test_groups_by_batch_before_chunking(self):
        """A chunk boundary never spans more than one broadcast batch, even
        across the recovery sweep's global query."""
        email_a1, email_a2, email_b1 = uuid4(), uuid4(), uuid4()
        publisher = BroadcastOutboxPublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_pending_older_than_with_batch.return_value = [
            (email_a1, "batch-a"),
            (email_a2, "batch-a"),
            (email_b1, "batch-b"),
        ]

        with (
            patch(
                "app.services.broadcast_outbox_publisher.get_settings"
            ) as mock_settings,
            patch(
                "app.tasks.send_broadcast_chunk_task.send_broadcast_chunk_task"
            ) as mock_task,
        ):
            mock_settings.return_value.broadcast_chunk_size = 100
            dispatched = publisher.run_recovery_sweep()

        assert dispatched == 3
        # One dispatch per batch, not one combined chunk across batches.
        assert mock_task.delay.call_count == 2
        dispatched_groups = [set(call[0][0]) for call in mock_task.delay.call_args_list]
        assert {str(email_a1), str(email_a2)} in dispatched_groups
        assert {str(email_b1)} in dispatched_groups

    def test_no_stale_entries_dispatches_nothing(self):
        publisher = BroadcastOutboxPublisher(db=MagicMock())
        publisher.repo = MagicMock()
        publisher.repo.get_pending_older_than_with_batch.return_value = []

        dispatched = publisher.run_recovery_sweep()

        assert dispatched == 0
