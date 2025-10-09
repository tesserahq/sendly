import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderUpdate
from app.services.provider_service import ProviderService


@pytest.fixture
def sample_provider_data():
    """Sample provider data for testing."""
    return {
        "name": "AWS SES",
    }


@pytest.fixture
def sample_provider(db: Session, sample_provider_data):
    """Create a sample provider in the database."""
    provider = Provider(**sample_provider_data)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def test_create_provider(db: Session, sample_provider_data):
    """Test creating a new provider."""
    # Create provider
    provider_create = ProviderCreate(**sample_provider_data)
    provider = ProviderService(db).create_provider(provider_create)

    # Assertions
    assert provider.id is not None
    assert provider.name == sample_provider_data["name"]
    assert provider.created_at is not None
    assert provider.updated_at is not None


def test_get_provider(db: Session, sample_provider):
    """Test getting a provider by ID."""
    # Get provider
    retrieved_provider = ProviderService(db).get_provider(sample_provider.id)

    # Assertions
    assert retrieved_provider is not None
    assert retrieved_provider.id == sample_provider.id
    assert retrieved_provider.name == sample_provider.name


def test_get_provider_by_name(db: Session, sample_provider):
    """Test getting a provider by name."""
    # Get provider by name
    retrieved_provider = ProviderService(db).get_provider_by_name(sample_provider.name)

    # Assertions
    assert retrieved_provider is not None
    assert retrieved_provider.id == sample_provider.id
    assert retrieved_provider.name == sample_provider.name


def test_get_providers(db: Session, sample_provider):
    """Test getting a list of providers."""
    # Get all providers
    providers = ProviderService(db).get_providers()

    # Assertions
    assert len(providers) >= 1
    assert any(p.id == sample_provider.id for p in providers)


def test_get_providers_with_pagination(db: Session, sample_provider):
    """Test getting providers with pagination."""
    provider_service = ProviderService(db)

    # Create additional providers
    for i in range(5):
        provider_create = ProviderCreate(name=f"Test Provider {i}")
        provider_service.create_provider(provider_create)

    # Test pagination
    first_page = provider_service.get_providers(skip=0, limit=2)
    second_page = provider_service.get_providers(skip=2, limit=2)

    # Assertions
    assert len(first_page) == 2
    assert len(second_page) == 2
    assert first_page[0].id != second_page[0].id


def test_update_provider(db: Session, sample_provider):
    """Test updating a provider."""
    # Update data
    update_data = {
        "name": "Mailgun",
    }
    provider_update = ProviderUpdate(**update_data)

    # Update provider
    updated_provider = ProviderService(db).update_provider(
        sample_provider.id, provider_update
    )

    # Assertions
    assert updated_provider is not None
    assert updated_provider.id == sample_provider.id
    assert updated_provider.name == update_data["name"]


def test_update_provider_partial(db: Session, sample_provider):
    """Test partially updating a provider."""
    original_name = sample_provider.name

    # Partial update (empty update)
    provider_update = ProviderUpdate()
    updated_provider = ProviderService(db).update_provider(
        sample_provider.id, provider_update
    )

    # Assertions - nothing should change
    assert updated_provider is not None
    assert updated_provider.name == original_name


def test_delete_provider(db: Session, sample_provider):
    """Test soft deleting a provider."""
    provider_service = ProviderService(db)

    # Delete provider
    success = provider_service.delete_provider(sample_provider.id)

    # Assertions
    assert success is True
    deleted_provider = provider_service.get_provider(sample_provider.id)
    assert deleted_provider is None


def test_provider_not_found_cases(db: Session):
    """Test various not found cases."""
    provider_service = ProviderService(db)

    # Test various not found cases
    non_existent_id = uuid4()

    # Get non-existent provider
    assert provider_service.get_provider(non_existent_id) is None

    # Get by non-existent name
    assert provider_service.get_provider_by_name("nonexistent") is None

    # Update non-existent provider
    update_data = {"name": "Updated Name"}
    provider_update = ProviderUpdate(**update_data)
    assert provider_service.update_provider(non_existent_id, provider_update) is None

    # Delete non-existent provider
    assert provider_service.delete_provider(non_existent_id) is False


def test_search_providers_with_filters(db: Session, sample_provider):
    """Test searching providers with dynamic filters."""
    # Search using ilike filter on name
    filters = {"name": {"operator": "ilike", "value": f"%{sample_provider.name[:3]}%"}}
    results = ProviderService(db).search(filters)

    assert isinstance(results, list)
    assert any(provider.id == sample_provider.id for provider in results)

    # Search using exact match
    filters = {"name": sample_provider.name}
    results = ProviderService(db).search(filters)

    assert len(results) == 1
    assert results[0].id == sample_provider.id

    # Search with no match
    filters = {"name": {"operator": "==", "value": "nonexistentprovider"}}
    results = ProviderService(db).search(filters)

    assert len(results) == 0


def test_search_providers_empty_filters(db: Session, sample_provider):
    """Test searching providers with empty filters."""
    filters = {}
    results = ProviderService(db).search(filters)

    # Should return all providers when filters are empty
    assert isinstance(results, list)
    assert len(results) >= 1
    assert any(provider.id == sample_provider.id for provider in results)


def test_create_duplicate_provider_name(db: Session, sample_provider_data):
    """Test that creating a provider with duplicate name raises an error."""
    provider_service = ProviderService(db)

    # Create first provider
    provider_create = ProviderCreate(**sample_provider_data)
    provider_service.create_provider(provider_create)

    # Try to create another provider with the same name
    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
        duplicate_provider = ProviderCreate(**sample_provider_data)
        provider_service.create_provider(duplicate_provider)


def test_soft_delete_and_restore(db: Session, sample_provider):
    """Test soft deleting and restoring a provider."""
    provider_service = ProviderService(db)

    # Soft delete the provider
    success = provider_service.delete_provider(sample_provider.id)
    assert success is True

    # Verify it's not returned by normal queries
    retrieved = provider_service.get_provider(sample_provider.id)
    assert retrieved is None

    # Verify it's in the deleted records
    deleted_provider = provider_service.get_deleted_record(sample_provider.id)
    assert deleted_provider is not None
    assert deleted_provider.id == sample_provider.id

    # Restore the provider
    restored = provider_service.restore_record(sample_provider.id)
    assert restored is True

    # Verify it's now returned by normal queries
    retrieved = provider_service.get_provider(sample_provider.id)
    assert retrieved is not None
    assert retrieved.id == sample_provider.id
