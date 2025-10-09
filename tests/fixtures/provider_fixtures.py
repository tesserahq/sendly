import pytest
from app.models.provider import Provider


@pytest.fixture(scope="function")
def setup_provider(db, faker):
    """Create a test provider for use in tests."""
    provider_data = {
        "name": faker.company(),
    }

    provider = Provider(**provider_data)
    db.add(provider)
    db.commit()
    db.refresh(provider)

    return provider


@pytest.fixture(scope="function")
def setup_another_provider(db, faker):
    """Create another test provider for use in tests."""
    provider_data = {
        "name": faker.company(),
    }

    provider = Provider(**provider_data)
    db.add(provider)
    db.commit()
    db.refresh(provider)

    return provider
