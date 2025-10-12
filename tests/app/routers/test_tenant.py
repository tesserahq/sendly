from uuid import uuid4
from fastapi import status

from app.services.tenant_service import TenantService


class TestTenantRouter:
    """Test suite for tenant router endpoints."""

    def test_create_tenant(self, client, setup_provider):
        """Test creating a new tenant."""
        tenant_data = {
            "name": "Test Tenant",
            "provider_id": str(setup_provider.id),
            "provider_settings": {"api_key": "test-key"},
        }

        response = client.post("/tenants", json=tenant_data)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == tenant_data["name"]
        assert data["provider_id"] == tenant_data["provider_id"]
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    def test_create_tenant_duplicate_name(self, client, setup_tenant):
        """Test creating a tenant with duplicate name fails."""
        tenant_data = {
            "name": setup_tenant.name,
            "provider_id": str(setup_tenant.provider_id),
            "provider_settings": {"api_key": "test-key"},
        }

        response = client.post("/tenants", json=tenant_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    def test_list_tenants(self, client, setup_tenant):
        """Test listing tenants with pagination."""
        response = client.get("/tenants")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert len(data["items"]) > 0

    def test_list_tenants_with_params(self, client, setup_tenant):
        """Test listing tenants with pagination parameters."""
        response = client.get("/tenants?page=1&size=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 1
        assert data["size"] == 10

    def test_get_tenant(self, client, setup_tenant):
        """Test getting a tenant by ID."""
        response = client.get(f"/tenants/{setup_tenant.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(setup_tenant.id)
        assert data["name"] == setup_tenant.name
        assert data["provider_id"] == str(setup_tenant.provider_id)

    def test_get_tenant_not_found(self, client):
        """Test getting a non-existent tenant returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/tenants/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_update_tenant(self, client, setup_tenant):
        """Test updating a tenant."""
        update_data = {
            "name": "Updated Tenant Name",
            "provider_settings": {"api_key": "updated-key"},
        }

        response = client.put(f"/tenants/{setup_tenant.id}", json=update_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["id"] == str(setup_tenant.id)

    def test_update_tenant_duplicate_name(self, client, setup_tenant, setup_provider):
        """Test updating a tenant with duplicate name fails."""
        # Create another tenant
        another_tenant_data = {
            "name": "Another Tenant",
            "provider_id": str(setup_provider.id),
            "provider_settings": {"api_key": "test-key"},
        }
        response = client.post("/tenants", json=another_tenant_data)
        assert response.status_code == status.HTTP_201_CREATED
        another_tenant_id = response.json()["id"]

        # Try to update the second tenant with the first tenant's name
        update_data = {"name": setup_tenant.name}
        response = client.put(f"/tenants/{another_tenant_id}", json=update_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    def test_update_tenant_not_found(self, client):
        """Test updating a non-existent tenant returns 404."""
        non_existent_id = uuid4()
        update_data = {"name": "Updated Name"}

        response = client.put(f"/tenants/{non_existent_id}", json=update_data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_delete_tenant(self, client, setup_tenant, db):
        """Test deleting a tenant (soft delete)."""
        tenant_id = setup_tenant.id

        response = client.delete(f"/tenants/{tenant_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify tenant is soft deleted
        tenant_service = TenantService(db)
        db_tenant = tenant_service.get_deleted_tenant(tenant_id)
        assert db_tenant is not None
        assert db_tenant.deleted_at is not None

    def test_delete_tenant_not_found(self, client):
        """Test deleting a non-existent tenant returns 404."""
        non_existent_id = uuid4()

        response = client.delete(f"/tenants/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_tenant_lifecycle(self, client, setup_provider, db):
        """Test complete tenant lifecycle: create, read, update, delete."""
        # Create
        tenant_data = {
            "name": "Lifecycle Test Tenant",
            "provider_id": str(setup_provider.id),
            "provider_settings": {"api_key": "test-key"},
        }
        create_response = client.post("/tenants", json=tenant_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        tenant_id = create_response.json()["id"]

        # Read
        get_response = client.get(f"/tenants/{tenant_id}")
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["name"] == tenant_data["name"]

        # Update
        update_data = {"name": "Updated Lifecycle Tenant"}
        update_response = client.put(f"/tenants/{tenant_id}", json=update_data)
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["name"] == update_data["name"]

        # Delete
        delete_response = client.delete(f"/tenants/{tenant_id}")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Verify soft delete
        tenant_service = TenantService(db)
        db_tenant = tenant_service.get_deleted_tenant(tenant_id)
        assert db_tenant.deleted_at is not None
