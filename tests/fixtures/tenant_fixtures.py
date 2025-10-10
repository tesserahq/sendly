import pytest
from app.models.tenant import Tenant


@pytest.fixture(scope="function")
def setup_tenant(db, setup_provider, faker):
    """Create a test tenant for use in tests."""
    tenant_data = {
        "name": faker.company(),
        "provider_id": setup_provider.id,
        "provider_settings": {
            "api_key": faker.password(length=32),
            "region": faker.random_element(["us-east-1", "us-west-2", "eu-west-1"]),
            "endpoint": faker.url(),
        },
    }

    tenant = Tenant(**tenant_data)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return tenant


@pytest.fixture(scope="function")
def setup_another_tenant(db, setup_provider, faker):
    """Create another test tenant for use in tests."""
    tenant_data = {
        "name": faker.company(),
        "provider_id": setup_provider.id,
        "provider_settings": {
            "api_key": faker.password(length=32),
            "region": faker.random_element(["us-east-1", "us-west-2", "eu-west-1"]),
            "endpoint": faker.url(),
        },
    }

    tenant = Tenant(**tenant_data)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return tenant
