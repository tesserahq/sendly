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

    def test_missing_subject_is_rejected_immediately(self, broadcast_client):
        project_id = uuid4()
        response = broadcast_client.post(
            "/broadcasts/send", json=_payload(project_id, subject=None)
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_recipients_is_rejected(self, broadcast_client):
        project_id = uuid4()
        response = broadcast_client.post(
            "/broadcasts/send", json=_payload(project_id, recipients=[])
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_omitting_project_id_creates_a_global_broadcast(self, broadcast_client):
        """project_id is optional to support org-wide, non-project-scoped
        broadcasts (requires a "*"-domain RBAC grant in Custos, mocked as
        always-authorized in tests)."""
        payload = _payload(uuid4())
        del payload["project_id"]

        with patched_providers():
            response = broadcast_client.post("/broadcasts/send", json=payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["queued_count"] == 2


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
        assert data["finished"] is True

    def test_get_broadcast_not_finished_until_send_stage_runs(self, broadcast_client):
        """Prepare-only: every Email/outbox row exists but nothing sent yet."""
        project_id = uuid4()
        with (
            patch(
                "app.tasks.prepare_broadcast_chunk_task.get_default_provider"
            ) as prep,
            patch("app.tasks.prepare_broadcast_chunk_task.BroadcastOutboxPublisher"),
        ):
            prep.return_value.provider_id = "postmark"
            send_response = broadcast_client.post(
                "/broadcasts/send", json=_payload(project_id)
            )
        batch_id = send_response.json()["batch_id"]

        response = broadcast_client.get(
            f"/broadcasts/{batch_id}", params={"project_id": str(project_id)}
        )

        data = response.json()
        assert data["prepared_count"] == 2
        assert data["finished"] is False

    def test_get_broadcast_finished_immediately_when_fully_suppressed(
        self, broadcast_client, real_db
    ):
        from datetime import datetime, timezone

        from app.models.email_suppression import EmailSuppression

        project_id = uuid4()
        real_db.add(
            EmailSuppression(
                project_id=project_id,
                email="suppressed@example.com",
                unsubscribed_at=datetime.now(timezone.utc),
                source="test",
            )
        )
        real_db.commit()

        response = broadcast_client.post(
            "/broadcasts/send",
            json=_payload(
                project_id,
                recipients=[{"email": "suppressed@example.com"}],
            ),
        )
        batch_id = response.json()["batch_id"]
        assert response.json()["queued_count"] == 0
        assert response.json()["suppressed_count"] == 1

        status_response = broadcast_client.get(
            f"/broadcasts/{batch_id}", params={"project_id": str(project_id)}
        )
        data = status_response.json()
        assert data["prepared_count"] == 0
        assert data["finished"] is True

    def test_get_broadcast_not_found(self, broadcast_client):
        response = broadcast_client.get(
            f"/broadcasts/{uuid4()}", params={"project_id": str(uuid4())}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_broadcast_does_not_require_project_id(self, broadcast_client):
        """batch_id is server-generated and globally unique — a caller with a
        global/super-admin RBAC grant can query it without project_id, same
        as GET /emails/{id} already allows."""
        project_id = uuid4()
        with patched_providers():
            send_response = broadcast_client.post(
                "/broadcasts/send", json=_payload(project_id)
            )
        batch_id = send_response.json()["batch_id"]

        response = broadcast_client.get(f"/broadcasts/{batch_id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["batch_id"] == batch_id

    def test_get_broadcast_lookup_ignores_mismatched_project_id(self, broadcast_client):
        """batch_id alone determines identity — passing an unrelated
        project_id (e.g. for RBAC scoping purposes only) doesn't affect
        which batch is returned."""
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
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["batch_id"] == batch_id

    def test_get_broadcast_authorizes_against_actual_project_not_caller_supplied(
        self, broadcast_client
    ):
        """Regression test for an IDOR: authorization must be checked against
        the batch's real project_id, never a caller-supplied one — otherwise
        a caller could read another project's batch by passing their own
        (validly-authorized) project_id in the query string, since batch_id
        alone no longer scopes the DB lookup."""
        real_project_id = uuid4()
        someone_elses_project_id = uuid4()
        with patched_providers():
            send_response = broadcast_client.post(
                "/broadcasts/send", json=_payload(real_project_id)
            )
        batch_id = send_response.json()["batch_id"]

        captured_domains = []

        def fake_authorize(*, resource, action, domain_resolver):
            async def dependency(request):
                captured_domains.append(await domain_resolver(request))
                return True

            return dependency

        with patch("app.routers.broadcast.authorize", side_effect=fake_authorize):
            response = broadcast_client.get(
                f"/broadcasts/{batch_id}",
                params={"project_id": str(someone_elses_project_id)},
            )

        assert response.status_code == status.HTTP_200_OK
        assert captured_domains == [str(real_project_id)]

    def test_get_broadcast_for_global_batch_authorizes_against_wildcard_domain(
        self, broadcast_client
    ):
        """A global batch (project_id=None) has no real project_id to
        authorize against, so the read check must fall back to the same
        "*" wildcard domain used to authorize sending it — not str(None)."""
        payload = _payload(uuid4())
        del payload["project_id"]
        with patched_providers():
            send_response = broadcast_client.post("/broadcasts/send", json=payload)
        batch_id = send_response.json()["batch_id"]

        captured_domains = []

        def fake_authorize(*, resource, action, domain_resolver):
            async def dependency(request):
                captured_domains.append(await domain_resolver(request))
                return True

            return dependency

        with patch("app.routers.broadcast.authorize", side_effect=fake_authorize):
            response = broadcast_client.get(f"/broadcasts/{batch_id}")

        assert response.status_code == status.HTTP_200_OK
        assert captured_domains == ["*"]
