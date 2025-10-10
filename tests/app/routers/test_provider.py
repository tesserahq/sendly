from uuid import uuid4
from fastapi import status

from app.services.provider_service import ProviderService


class TestProviderRouter:
    """Test suite for provider router endpoints."""

    def test_create_provider(self, client):
        """Test creating a new provider."""
        provider_data = {
            "name": "Test Provider",
        }

        response = client.post("/providers", json=provider_data)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == provider_data["name"]
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    def test_create_provider_duplicate_name(self, client, setup_provider):
        """Test creating a provider with duplicate name fails."""
        provider_data = {
            "name": setup_provider.name,
        }

        response = client.post("/providers", json=provider_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    def test_list_providers(self, client, setup_provider):
        """Test listing providers with pagination."""
        response = client.get("/providers")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert len(data["items"]) > 0

    def test_list_providers_with_params(self, client, setup_provider):
        """Test listing providers with pagination parameters."""
        response = client.get("/providers?page=1&size=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10

    def test_get_provider(self, client, setup_provider):
        """Test getting a provider by ID."""
        response = client.get(f"/providers/{setup_provider.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(setup_provider.id)
        assert data["name"] == setup_provider.name

    def test_get_provider_not_found(self, client):
        """Test getting a non-existent provider returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/providers/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_update_provider(self, client, setup_provider):
        """Test updating a provider."""
        update_data = {
            "name": "Updated Provider Name",
        }

        response = client.put(f"/providers/{setup_provider.id}", json=update_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["id"] == str(setup_provider.id)

    def test_update_provider_duplicate_name(self, client, setup_provider):
        """Test updating a provider with duplicate name fails."""
        # Create another provider
        another_provider_data = {
            "name": "Another Provider",
        }
        response = client.post("/providers", json=another_provider_data)
        assert response.status_code == status.HTTP_201_CREATED
        another_provider_id = response.json()["id"]

        # Try to update the second provider with the first provider's name
        update_data = {"name": setup_provider.name}
        response = client.put(f"/providers/{another_provider_id}", json=update_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    def test_update_provider_not_found(self, client):
        """Test updating a non-existent provider returns 404."""
        non_existent_id = uuid4()
        update_data = {"name": "Updated Name"}

        response = client.put(f"/providers/{non_existent_id}", json=update_data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_delete_provider(self, client, setup_provider, db):
        """Test deleting a provider (soft delete)."""
        provider_id = setup_provider.id

        response = client.delete(f"/providers/{provider_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify provider is soft deleted
        db_provider = ProviderService(db).get_deleted_provider(provider_id)
        assert db_provider is not None
        assert db_provider.deleted_at is not None

    def test_delete_provider_not_found(self, client):
        """Test deleting a non-existent provider returns 404."""
        non_existent_id = uuid4()

        response = client.delete(f"/providers/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_provider_lifecycle(self, client, db):
        """Test complete provider lifecycle: create, read, update, delete."""
        # Create
        provider_data = {
            "name": "Lifecycle Test Provider",
        }
        create_response = client.post("/providers", json=provider_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        provider_id = create_response.json()["id"]

        # Read
        get_response = client.get(f"/providers/{provider_id}")
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["name"] == provider_data["name"]

        # Update
        update_data = {"name": "Updated Lifecycle Provider"}
        update_response = client.put(f"/providers/{provider_id}", json=update_data)
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["name"] == update_data["name"]

        # Delete
        delete_response = client.delete(f"/providers/{provider_id}")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Verify soft delete
        provider_service = ProviderService(db)
        db_provider = provider_service.get_deleted_provider(provider_id)
        assert db_provider.deleted_at is not None

    def test_list_providers_multiple_pages(self, client, db):
        """Test pagination with multiple providers."""
        # Create multiple providers
        for i in range(5):
            provider_data = {"name": f"Provider {i}"}
            client.post("/providers", json=provider_data)

        # Test first page
        response = client.get("/providers?page=1&size=2")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1
        assert data["size"] == 2
        assert data["total"] >= 5

        # Test second page
        response = client.get("/providers?page=2&size=2")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 2
