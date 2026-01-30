"""Tests for the providers router."""

from __future__ import annotations

from fastapi import status


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
