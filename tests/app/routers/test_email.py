from uuid import uuid4
from fastapi import status


class TestEmailRouter:
    """Test suite for email router endpoints."""

    def test_get_email(self, client, setup_email):
        """Test getting an email by ID."""
        response = client.get(f"/emails/{setup_email.id}")

        assert response.status_code == status.HTTP_200_OK
        email_data = response.json()

        assert email_data["id"] == str(setup_email.id)
        assert email_data["from_email"] == setup_email.from_email
        assert email_data["to_email"] == setup_email.to_email
        assert email_data["subject"] == setup_email.subject
        assert email_data["status"] == setup_email.status
        assert email_data["project_id"] == setup_email.project_id
        assert email_data["provider"] == setup_email.provider

    def test_get_email_not_found(self, client):
        """Test getting a non-existent email returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/emails/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()
