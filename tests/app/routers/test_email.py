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
        assert email_data["tenant_id"] == str(setup_email.tenant_id)
        assert email_data["provider_id"] == str(setup_email.provider_id)

    def test_get_email_not_found(self, client):
        """Test getting a non-existent email returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/emails/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_list_tenant_emails(self, client, setup_email, setup_tenant):
        """Test listing emails for a specific tenant."""
        response = client.get(f"/tenants/{setup_tenant.id}/emails")

        assert response.status_code == status.HTTP_200_OK
        paginated_data = response.json()

        assert "items" in paginated_data
        assert "total" in paginated_data
        assert "page" in paginated_data
        assert "size" in paginated_data
        assert len(paginated_data["items"]) > 0

        # Verify the email belongs to the tenant
        for email in paginated_data["items"]:
            assert email["tenant_id"] == str(setup_tenant.id)

    def test_list_tenant_emails_with_params(self, client, setup_email, setup_tenant):
        """Test listing tenant emails with pagination parameters."""
        response = client.get(f"/tenants/{setup_tenant.id}/emails?page=1&size=10")

        assert response.status_code == status.HTTP_200_OK
        paginated_data = response.json()

        assert paginated_data["page"] == 1
        assert paginated_data["size"] == 10

    def test_list_tenant_emails_not_found(self, client):
        """Test listing emails for a non-existent tenant returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/tenants/{non_existent_id}/emails")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_list_tenant_emails_multiple(
        self, client, setup_email, setup_another_email, setup_tenant, db
    ):
        """Test listing multiple emails for a tenant."""
        response = client.get(f"/tenants/{setup_tenant.id}/emails")

        assert response.status_code == status.HTTP_200_OK
        paginated_data = response.json()

        assert len(paginated_data["items"]) >= 2

        # Verify all emails belong to the same tenant
        for email in paginated_data["items"]:
            assert email["tenant_id"] == str(setup_tenant.id)

    def test_list_tenant_emails_empty(self, client, setup_provider, db, faker):
        """Test listing emails for a tenant with no emails."""
        from app.models.tenant import Tenant

        # Create a tenant with no emails
        tenant_data = {
            "name": faker.company(),
            "provider_id": setup_provider.id,
            "provider_settings": {"api_key": "test-key"},
        }
        tenant = Tenant(**tenant_data)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        response = client.get(f"/tenants/{tenant.id}/emails")

        assert response.status_code == status.HTTP_200_OK
        paginated_data = response.json()
        assert len(paginated_data["items"]) == 0
        assert paginated_data["total"] == 0

    def test_list_tenant_emails_ordering(
        self, client, setup_email, setup_another_email, setup_tenant
    ):
        """Test that emails are ordered by created_at descending."""
        response = client.get(f"/tenants/{setup_tenant.id}/emails")

        assert response.status_code == status.HTTP_200_OK
        paginated_data = response.json()

        items = paginated_data["items"]
        if len(items) > 1:
            # Verify descending order by created_at
            for i in range(len(items) - 1):
                current_created = items[i]["created_at"]
                next_created = items[i + 1]["created_at"]
                assert current_created >= next_created
