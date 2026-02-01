"""Tests for the providers router."""

from __future__ import annotations

from fastapi import status
from uuid import uuid4
from datetime import datetime, timezone


class TestProviderRouter:
    """Test suite for provider router endpoints."""

    def test_list_providers_returns_200_and_data(self, client):
        """GET /providers/ returns 200 and a list of registered providers."""
        response = client.get("/providers/")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "items" in body
        items = body["items"]
        assert isinstance(items, list)
        assert len(items) >= 1

        postmark = next((p for p in items if p["id"] == "postmark"), None)
        assert postmark is not None
        assert postmark["name"] == "Postmark"
        assert postmark["enabled"] is True
        assert postmark["default"] is True
        assert postmark["site"] == "https://postmarkapp.com"

    def test_list_providers_enabled_only(self, client):
        """GET /providers/?enabled_only=true returns only enabled providers."""
        response = client.get("/providers/?enabled_only=true")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        items = body["items"]
        for provider in items:
            assert provider["enabled"] is True

    def test_receive_delivery_events_postmark_success(self, client, db):
        """POST /providers/postmark/delivery-events processes a valid Postmark webhook."""
        from app.models.email import Email
        from app.constants.email import EmailStatus

        # Create an email first with a known provider_message_id
        provider_msg_id = "883953f4-6105-42a2-a16a-77a8eac79483"
        email = Email(
            id=uuid4(),
            from_email="sender@example.com",
            to_email="john@example.com",
            subject="Test Email",
            body="Test body",
            status=EmailStatus.SENT,
            provider="postmark",
            provider_message_id=provider_msg_id,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(email)
        db.commit()

        # Sample Postmark delivery webhook payload
        payload = {
            "RecordType": "Delivery",
            "MessageID": provider_msg_id,
            "Recipient": "john@example.com",
            "DeliveredAt": "2024-02-01T12:45:23Z",
            "Details": "Test delivery",
            "Tag": "welcome-email",
            "ServerID": 23,
        }

        response = client.post("/providers/postmark/delivery-events", json=payload)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "success"
        assert body["provider"] == "postmark"
        assert body["events_received"] == 1
        assert body["events_processed"] == 1
        assert body["events_failed"] == 0

    def test_receive_delivery_events_email_not_found(self, client):
        """POST /providers/postmark/delivery-events handles missing email gracefully."""
        # Sample Postmark delivery webhook payload with non-existent message ID
        payload = {
            "RecordType": "Delivery",
            "MessageID": "non-existent-message-id",
            "Recipient": "john@example.com",
            "DeliveredAt": "2024-02-01T12:45:23Z",
        }

        response = client.post("/providers/postmark/delivery-events", json=payload)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "partial_failure"
        assert body["events_received"] == 1
        assert body["events_processed"] == 0
        assert body["events_failed"] == 1
        assert body["failures"] is not None
        assert len(body["failures"]) == 1

    def test_receive_delivery_events_invalid_provider(self, client):
        """POST /providers/invalid/delivery-events returns 404 for unknown provider."""
        payload = {"RecordType": "Delivery", "MessageID": "test-123"}

        response = client.post("/providers/invalid/delivery-events", json=payload)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_receive_delivery_events_invalid_json(self, client):
        """POST /providers/postmark/delivery-events returns 400 for invalid JSON."""
        response = client.post(
            "/providers/postmark/delivery-events",
            data="invalid json{",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid json" in response.json()["detail"].lower()
