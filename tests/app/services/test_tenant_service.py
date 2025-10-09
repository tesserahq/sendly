import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.services.tenant_service import TenantService


@pytest.fixture
def sample_tenant_data(setup_provider):
    """Sample tenant data for testing."""
    return {
        "name": "Test Tenant",
        "provider_id": setup_provider.id,
        "provider_api_key": "test_api_key_12345",
        "provider_metadata": {
            "region": "us-east-1",
            "endpoint": "https://api.example.com",
        },
    }


@pytest.fixture
def sample_tenant(db: Session, sample_tenant_data):
    """Create a sample tenant in the database."""
    tenant = Tenant(**sample_tenant_data)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def test_create_tenant(db: Session, sample_tenant_data):
    """Test creating a new tenant."""
    # Create tenant
    tenant_create = TenantCreate(**sample_tenant_data)
    tenant = TenantService(db).create_tenant(tenant_create)

    # Assertions
    assert tenant.id is not None
    assert tenant.name == sample_tenant_data["name"]
    assert tenant.provider_id == sample_tenant_data["provider_id"]
    assert tenant.provider_api_key == sample_tenant_data["provider_api_key"]
    assert tenant.provider_metadata == sample_tenant_data["provider_metadata"]
    assert tenant.created_at is not None
    assert tenant.updated_at is not None


def test_get_tenant(db: Session, sample_tenant):
    """Test getting a tenant by ID."""
    # Get tenant
    retrieved_tenant = TenantService(db).get_tenant(sample_tenant.id)

    # Assertions
    assert retrieved_tenant is not None
    assert retrieved_tenant.id == sample_tenant.id
    assert retrieved_tenant.name == sample_tenant.name


def test_get_tenant_by_name(db: Session, sample_tenant):
    """Test getting a tenant by name."""
    # Get tenant by name
    retrieved_tenant = TenantService(db).get_tenant_by_name(sample_tenant.name)

    # Assertions
    assert retrieved_tenant is not None
    assert retrieved_tenant.id == sample_tenant.id
    assert retrieved_tenant.name == sample_tenant.name


def test_get_tenants(db: Session, sample_tenant):
    """Test getting a list of tenants."""
    # Get all tenants
    tenants = TenantService(db).get_tenants()

    # Assertions
    assert len(tenants) >= 1
    assert any(t.id == sample_tenant.id for t in tenants)


def test_get_tenants_with_pagination(db: Session, setup_provider):
    """Test getting tenants with pagination."""
    tenant_service = TenantService(db)

    # Create additional tenants
    for i in range(5):
        tenant_create = TenantCreate(
            name=f"Test Tenant {i}",
            provider_id=setup_provider.id,
            provider_api_key=f"api_key_{i}",
            provider_metadata={"index": i},
        )
        tenant_service.create_tenant(tenant_create)

    # Test pagination
    first_page = tenant_service.get_tenants(skip=0, limit=2)
    second_page = tenant_service.get_tenants(skip=2, limit=2)

    # Assertions
    assert len(first_page) == 2
    assert len(second_page) == 2
    assert first_page[0].id != second_page[0].id


def test_get_tenants_by_provider(db: Session, setup_provider, setup_another_provider):
    """Test getting tenants for a specific provider."""
    tenant_service = TenantService(db)

    # Create tenants for the first provider
    for i in range(3):
        tenant_create = TenantCreate(
            name=f"Provider 1 Tenant {i}",
            provider_id=setup_provider.id,
            provider_api_key=f"api_key_p1_{i}",
            provider_metadata={"provider": 1, "index": i},
        )
        tenant_service.create_tenant(tenant_create)

    # Create tenants for the second provider
    for i in range(2):
        tenant_create = TenantCreate(
            name=f"Provider 2 Tenant {i}",
            provider_id=setup_another_provider.id,
            provider_api_key=f"api_key_p2_{i}",
            provider_metadata={"provider": 2, "index": i},
        )
        tenant_service.create_tenant(tenant_create)

    # Get tenants for the first provider
    provider1_tenants = tenant_service.get_tenants_by_provider(setup_provider.id)
    provider2_tenants = tenant_service.get_tenants_by_provider(
        setup_another_provider.id
    )

    # Assertions
    assert len(provider1_tenants) == 3
    assert len(provider2_tenants) == 2
    assert all(t.provider_id == setup_provider.id for t in provider1_tenants)
    assert all(t.provider_id == setup_another_provider.id for t in provider2_tenants)


def test_update_tenant(db: Session, sample_tenant):
    """Test updating a tenant."""
    # Update data
    update_data = {
        "name": "Updated Tenant Name",
        "provider_api_key": "updated_api_key",
        "provider_metadata": {"region": "eu-west-1", "updated": True},
    }
    tenant_update = TenantUpdate(**update_data)

    # Update tenant
    updated_tenant = TenantService(db).update_tenant(sample_tenant.id, tenant_update)

    # Assertions
    assert updated_tenant is not None
    assert updated_tenant.id == sample_tenant.id
    assert updated_tenant.name == update_data["name"]
    assert updated_tenant.provider_api_key == update_data["provider_api_key"]
    assert updated_tenant.provider_metadata == update_data["provider_metadata"]


def test_update_tenant_partial(db: Session, sample_tenant):
    """Test partially updating a tenant."""
    original_name = sample_tenant.name
    original_api_key = sample_tenant.provider_api_key

    # Partial update (only metadata)
    tenant_update = TenantUpdate(provider_metadata={"updated": True})
    updated_tenant = TenantService(db).update_tenant(sample_tenant.id, tenant_update)

    # Assertions - name and api_key should remain unchanged
    assert updated_tenant is not None
    assert updated_tenant.name == original_name
    assert updated_tenant.provider_api_key == original_api_key
    assert updated_tenant.provider_metadata == {"updated": True}


def test_delete_tenant(db: Session, sample_tenant):
    """Test soft deleting a tenant."""
    tenant_service = TenantService(db)

    # Delete tenant
    success = tenant_service.delete_tenant(sample_tenant.id)

    # Assertions
    assert success is True
    deleted_tenant = tenant_service.get_tenant(sample_tenant.id)
    assert deleted_tenant is None


def test_tenant_not_found_cases(db: Session, setup_provider):
    """Test various not found cases."""
    tenant_service = TenantService(db)

    # Test various not found cases
    non_existent_id = uuid4()

    # Get non-existent tenant
    assert tenant_service.get_tenant(non_existent_id) is None

    # Get by non-existent name
    assert tenant_service.get_tenant_by_name("nonexistent") is None

    # Update non-existent tenant
    update_data = {"name": "Updated Name"}
    tenant_update = TenantUpdate(**update_data)
    assert tenant_service.update_tenant(non_existent_id, tenant_update) is None

    # Delete non-existent tenant
    assert tenant_service.delete_tenant(non_existent_id) is False


def test_search_tenants_with_filters(db: Session, sample_tenant):
    """Test searching tenants with dynamic filters."""
    # Search using ilike filter on name
    filters = {"name": {"operator": "ilike", "value": f"%{sample_tenant.name[:4]}%"}}
    results = TenantService(db).search(filters)

    assert isinstance(results, list)
    assert any(tenant.id == sample_tenant.id for tenant in results)

    # Search using exact match
    filters = {"name": sample_tenant.name}
    results = TenantService(db).search(filters)

    assert len(results) == 1
    assert results[0].id == sample_tenant.id

    # Search with no match
    filters = {"name": {"operator": "==", "value": "nonexistenttenant"}}
    results = TenantService(db).search(filters)

    assert len(results) == 0


def test_search_tenants_by_provider_filter(db: Session, sample_tenant):
    """Test searching tenants by provider ID."""
    filters = {"provider_id": sample_tenant.provider_id}
    results = TenantService(db).search(filters)

    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(t.provider_id == sample_tenant.provider_id for t in results)


def test_search_tenants_empty_filters(db: Session, sample_tenant):
    """Test searching tenants with empty filters."""
    filters = {}
    results = TenantService(db).search(filters)

    # Should return all tenants when filters are empty
    assert isinstance(results, list)
    assert len(results) >= 1
    assert any(tenant.id == sample_tenant.id for tenant in results)


def test_create_duplicate_tenant_name(db: Session, sample_tenant_data):
    """Test that creating a tenant with duplicate name raises an error."""
    tenant_service = TenantService(db)

    # Create first tenant
    tenant_create = TenantCreate(**sample_tenant_data)
    tenant_service.create_tenant(tenant_create)

    # Try to create another tenant with the same name
    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
        duplicate_tenant = TenantCreate(**sample_tenant_data)
        tenant_service.create_tenant(duplicate_tenant)


def test_soft_delete_and_restore(db: Session, sample_tenant):
    """Test soft deleting and restoring a tenant."""
    tenant_service = TenantService(db)

    # Soft delete the tenant
    success = tenant_service.delete_tenant(sample_tenant.id)
    assert success is True

    # Verify it's not returned by normal queries
    retrieved = tenant_service.get_tenant(sample_tenant.id)
    assert retrieved is None

    # Verify it's in the deleted records
    deleted_tenant = tenant_service.get_deleted_record(sample_tenant.id)
    assert deleted_tenant is not None
    assert deleted_tenant.id == sample_tenant.id

    # Restore the tenant
    restored = tenant_service.restore_record(sample_tenant.id)
    assert restored is True

    # Verify it's now returned by normal queries
    retrieved = tenant_service.get_tenant(sample_tenant.id)
    assert retrieved is not None
    assert retrieved.id == sample_tenant.id
