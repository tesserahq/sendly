"""Router tests for POST /broadcasts/send and GET /broadcasts/{batch_id}.

Uses `broadcast_client` (bound to `real_db`) because a successful send
dispatches Celery-eager tasks (prepare, then send) that each open their own
DB session — see conftest.py's `real_db` fixture docstring.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi import status

from app.providers.base import EmailSendResult


@contextmanager
def patched_providers():
    """Stub out the provider factory in both the prepare and send tasks so a
    full accept -> prepare -> send pipeline run doesn't need a real Postmark
    API key or network access."""
    with (
        patch("app.tasks.prepare_broadcast_chunk_task.get_default_provider") as prep,
        patch("app.tasks.send_broadcast_chunk_task.get_default_provider") as send,
    ):
        prep.return_value.provider_id = "postmark"
        send.return_value.provider_id = "postmark"
        send.return_value.send_batch.side_effect = lambda requests: [
            EmailSendResult(ok=True, provider_message_id=f"pm-{i}")
            for i in range(len(requests))
        ]
        yield


def _payload(project_id, **overrides):
    defaults = dict(
        project_id=str(project_id),
        from_email="sender@example.com",
        subject="Hello",
        html="<p>Hi ${first_name}</p>",
        recipients=[
            {"email": "a@example.com", "first_name": "Alice"},
            {"email": "b@example.com", "first_name": "Bob"},
        ],
    )
    defaults.update(overrides)
    return defaults


class TestSendBroadcast:
    def test_send_broadcast_returns_counts_immediately(self, broadcast_client):
        project_id = uuid4()
        with patched_providers():
            response = broadcast_client.post(
                "/broadcasts/send", json=_payload(project_id)
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["queued_count"] == 2
        assert data["suppressed_count"] == 0
        assert data["batch_id"]

    def test_idempotency_key_returns_original_batch(self, broadcast_client):
        project_id = uuid4()
        body = _payload(project_id, idempotency_key="retry-key")

        with patched_providers():
            first = broadcast_client.post("/broadcasts/send", json=body)
            second = broadcast_client.post("/broadcasts/send", json=body)

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.json()["batch_id"] == second.json()["batch_id"]

    def test_idempotency_key_conflict_on_different_content(self, broadcast_client):
        project_id = uuid4()
        with patched_providers():
            broadcast_client.post(
                "/broadcasts/send",
                json=_payload(project_id, idempotency_key="same-key"),
            )
            response = broadcast_client.post(
                "/broadcasts/send",
                json=_payload(
                    project_id, idempotency_key="same-key", subject="Different"
                ),
            )

        assert response.status_code == status.HTTP_409_CONFLICT


class TestGetBroadcast:
    def test_get_broadcast_reports_prepared_count(self, broadcast_client):
        project_id = uuid4()
        with patched_providers():
            send_response = broadcast_client.post(
                "/broadcasts/send", json=_payload(project_id)
            )
        batch_id = send_response.json()["batch_id"]

        response = broadcast_client.get(
            f"/broadcasts/{batch_id}", params={"project_id": str(project_id)}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["batch_id"] == batch_id
        assert data["queued_count"] == 2
        assert data["prepared_count"] == 2

    def test_get_broadcast_not_found(self, broadcast_client):
        response = broadcast_client.get(
            f"/broadcasts/{uuid4()}", params={"project_id": str(uuid4())}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_broadcast_scoped_by_project(self, broadcast_client):
        project_id = uuid4()
        other_project_id = uuid4()
        with patched_providers():
            send_response = broadcast_client.post(
                "/broadcasts/send", json=_payload(project_id)
            )
        batch_id = send_response.json()["batch_id"]

        response = broadcast_client.get(
            f"/broadcasts/{batch_id}", params={"project_id": str(other_project_id)}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
